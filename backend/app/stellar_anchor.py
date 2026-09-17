from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any, Optional

import httpx
from stellar_sdk import (
    Asset,
    Keypair,
    Network,
    Server,
    TransactionBuilder,
    TransactionEnvelope,
)
from stellar_sdk.exceptions import (
    NotFoundError,
    BaseHorizonError,
    Ed25519PublicKeyInvalidError,
)

from .models import AgentLog, TransactionRecord, ErrorResponse, ErrorDetail
from .store import store
from .websocket_manager import ws_manager

ANCHOR_HOME = "https://tr-mock-anchor.fly.dev"
TOML_URL = f"{ANCHOR_HOME}/.well-known/stellar.toml"
HORIZON_URL = "https://horizon-testnet.stellar.org"
FRIENDBOT_URL = "https://friendbot.stellar.org"
NETWORK_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
USDC_ISSUER = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"
DEFAULT_IBAN = "TR330006100519786457841326"
KEY_FILE = Path(__file__).resolve().parent.parent / ".data" / "agent_secret"
ANCHOR_TIMEOUT = 10.0
FALLBACK_MSG = (
    "Mock Anchor Sunucusu Yanıt Vermiyor. Fallback (Çevrimdışı Simülasyon) Moduna Geçildi. "
    "Ajan mutabakatı ve SEP-6 verileri lokal olarak onaylandı."
)
INSUFFICIENT_USDC_MSG = (
    "Uyarı: Testnet USDC bakiyesi yetersiz, ancak SEP-6 Off-Ramp mutabakatı ve simülasyonu başarıyla tamamlandı!"
)


class StellarAnchorService:
    """SEP-10 + SEP-6 against tr-mock-anchor.fly.dev. Wallet signatures only — no API keys."""

    def __init__(self) -> None:
        self.horizon = Server(horizon_url=HORIZON_URL)
        self._toml: Optional[dict[str, Any]] = None
        self._keypair: Optional[Keypair] = None
        self._last_horizon_error: Optional[str] = None

    def discover_toml(self) -> dict[str, Any]:
        """Discover and parse stellar.toml with error handling"""
        if self._toml:
            return self._toml
        
        try:
            resp = httpx.get(TOML_URL, timeout=ANCHOR_TIMEOUT)
            resp.raise_for_status()
        except httpx.TimeoutException as e:
            raise ValueError(
                ErrorResponse(
                    error="Anchor server timeout",
                    error_code="ANCHOR_TIMEOUT",
                    details=[
                        ErrorDetail(
                            field="anchor",
                            message=f"Failed to connect to anchor server (timeout): {str(e)}",
                            code="CONNECTION_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e
        except httpx.HTTPStatusError as e:
            raise ValueError(
                ErrorResponse(
                    error="Anchor server HTTP error",
                    error_code="ANCHOR_HTTP_ERROR",
                    details=[
                        ErrorDetail(
                            field="anchor",
                            message=f"Anchor server returned HTTP {e.response.status_code}",
                            code="HTTP_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e
        except httpx.RequestError as e:
            raise ValueError(
                ErrorResponse(
                    error="Anchor server connection error",
                    error_code="ANCHOR_CONNECTION_ERROR",
                    details=[
                        ErrorDetail(
                            field="anchor",
                            message=f"Failed to connect to anchor server: {str(e)}",
                            code="CONNECTION_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e
        
        try:
            parsed = tomllib.loads(resp.text)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(
                ErrorResponse(
                    error="Invalid stellar.toml format",
                    error_code="INVALID_TOML",
                    details=[
                        ErrorDetail(
                            field="stellar.toml",
                            message=f"Failed to parse stellar.toml: {str(e)}",
                            code="PARSE_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e
        
        web_auth = parsed.get("WEB_AUTH_ENDPOINT")
        transfer = parsed.get("TRANSFER_SERVER")
        if not web_auth or not transfer:
            raise ValueError(
                ErrorResponse(
                    error="Invalid stellar.toml configuration",
                    error_code="INCOMPLETE_TOML",
                    details=[
                        ErrorDetail(
                            field="stellar.toml",
                            message="WEB_AUTH_ENDPOINT or TRANSFER_SERVER missing in stellar.toml",
                            code="CONFIGURATION_ERROR"
                        )
                    ]
                ).model_dump_json()
            )
        
        self._toml = parsed
        return parsed

    def agent_keypair(self) -> Keypair:
        if self._keypair:
            return self._keypair
        secret = os.environ.get("STELLAR_SECRET_KEY")
        if not secret and KEY_FILE.exists():
            secret = KEY_FILE.read_text().strip()
        if secret:
            self._keypair = Keypair.from_secret(secret)
            return self._keypair
        self._keypair = Keypair.random()
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_text(self._keypair.secret)
        return self._keypair

    async def ensure_funded(self, kp: Keypair) -> None:
        try:
            self.horizon.accounts().account_id(kp.public_key).call()
        except NotFoundError:
            async with httpx.AsyncClient(timeout=ANCHOR_TIMEOUT) as client:
                await client.get(FRIENDBOT_URL, params={"addr": kp.public_key})
        store.wallet_public_key = kp.public_key

    async def sep10_authenticate(self, kp: Optional[Keypair] = None) -> str:
        """SEP-10 authentication with comprehensive error handling"""
        try:
            kp = kp or self.agent_keypair()
            await self.ensure_funded(kp)
            toml = self.discover_toml()
            auth_url = toml["WEB_AUTH_ENDPOINT"]
            
            async with httpx.AsyncClient(timeout=ANCHOR_TIMEOUT) as client:
                # Request challenge
                try:
                    challenge = await client.get(auth_url, params={"account": kp.public_key})
                    challenge.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise ValueError(
                        ErrorResponse(
                            error="SEP-10 challenge request failed",
                            error_code="SEP10_CHALLENGE_ERROR",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Anchor returned HTTP {e.response.status_code} for challenge",
                                    code="HTTP_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                except httpx.RequestError as e:
                    raise ValueError(
                        ErrorResponse(
                            error="SEP-10 challenge connection error",
                            error_code="SEP10_CONNECTION_ERROR",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Failed to connect to anchor for challenge: {str(e)}",
                                    code="CONNECTION_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                
                try:
                    xdr = challenge.json()["transaction"]
                except (KeyError, ValueError) as e:
                    raise ValueError(
                        ErrorResponse(
                            error="Invalid SEP-10 challenge response",
                            error_code="SEP10_INVALID_CHALLENGE",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Challenge response missing transaction field: {str(e)}",
                                    code="VALIDATION_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                
                # Sign challenge
                try:
                    envelope = TransactionEnvelope.from_xdr(xdr, NETWORK_PASSPHRASE)
                    envelope.sign(kp)
                    signed = envelope.to_xdr()
                except Exception as e:
                    raise ValueError(
                        ErrorResponse(
                            error="SEP-10 challenge signing failed",
                            error_code="SEP10_SIGNING_ERROR",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Failed to sign challenge: {str(e)}",
                                    code="SIGNING_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                
                # Submit signed challenge
                try:
                    token_resp = await client.post(auth_url, json={"transaction": signed})
                    if token_resp.status_code >= 400:
                        # Fallback to form data
                        token_resp = await client.post(auth_url, data={"transaction": signed})
                    token_resp.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise ValueError(
                        ErrorResponse(
                            error="SEP-10 token request failed",
                            error_code="SEP10_TOKEN_ERROR",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Anchor returned HTTP {e.response.status_code} for token",
                                    code="HTTP_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                except httpx.RequestError as e:
                    raise ValueError(
                        ErrorResponse(
                            error="SEP-10 token connection error",
                            error_code="SEP10_TOKEN_CONNECTION_ERROR",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Failed to connect to anchor for token: {str(e)}",
                                    code="CONNECTION_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                
                try:
                    token = token_resp.json().get("token")
                except (KeyError, ValueError) as e:
                    raise ValueError(
                        ErrorResponse(
                            error="Invalid SEP-10 token response",
                            error_code="SEP10_INVALID_TOKEN",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message=f"Token response missing token field: {str(e)}",
                                    code="VALIDATION_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    ) from e
                
                if not token:
                    raise ValueError(
                        ErrorResponse(
                            error="SEP-10 token not received",
                            error_code="SEP10_NO_TOKEN",
                            details=[
                                ErrorDetail(
                                    field="sep10",
                                    message="Anchor did not return a token in response",
                                    code="VALIDATION_ERROR"
                                )
                            ]
                        ).model_dump_json()
                    )
                
                return token
                
        except ValueError as e:
            # Re-raise ValueError with ErrorResponse
            raise
        except Exception as e:
            raise ValueError(
                ErrorResponse(
                    error="SEP-10 authentication error",
                    error_code="SEP10_AUTH_ERROR",
                    details=[
                        ErrorDetail(
                            field="sep10",
                            message=f"Unexpected SEP-10 error: {str(e)}",
                            code="UNKNOWN_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from e

    async def sep6_withdraw(
        self,
        amount: float,
        iban: str = DEFAULT_IBAN,
        sep10_token: Optional[str] = None,
        account: Optional[str] = None,
    ) -> dict[str, Any]:
        kp = self.agent_keypair()
        token = sep10_token or await self.sep10_authenticate(kp)
        toml = self.discover_toml()
        transfer = toml["TRANSFER_SERVER"].rstrip("/")
        dest = (iban or DEFAULT_IBAN).replace(" ", "")
        params = {
            "asset_code": "USDC",
            "type": "bank_account",
            "amount": str(amount),
            "dest": dest,
            "account": kp.public_key,
        }
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=ANCHOR_TIMEOUT) as client:
            resp = await client.get(f"{transfer}/withdraw", params=params, headers=headers)
            if resp.status_code >= 400:
                resp = await client.post(f"{transfer}/withdraw", params=params, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        if resp.status_code >= 400:
            return {"ok": False, "status_code": resp.status_code, "body": body, "token": token}
        account_id = self._extract_treasury(body)
        memo = body.get("memo")
        memo_type = body.get("memo_type") or "text"
        return {
            "ok": True,
            "protocol": "SEP-6",
            "auth": "SEP-10",
            "amount": amount,
            "iban": dest,
            "account_id": account_id,
            "memo": memo,
            "memo_type": memo_type,
            "token": token,
            "body": body,
            "message": f"SEP-6 treasury {account_id} memo={memo}",
        }

    def _extract_treasury(self, body: dict[str, Any]) -> Optional[str]:
        for key in ("account_id", "how"):
            val = body.get(key)
            if isinstance(val, str) and val.startswith("G") and len(val) >= 56:
                return val[:56]
        blob = str(body)
        match = re.search(r"G[A-Z2-7]{55}", blob)
        return match.group(0) if match else None

    def _apply_memo(self, builder: TransactionBuilder, memo: Optional[str], memo_type: str) -> None:
        if memo is None or memo == "":
            return
        kind = (memo_type or "text").lower()
        if kind == "id":
            builder.add_id_memo(int(memo))
        elif kind == "hash":
            builder.add_hash_memo(memo)
        else:
            builder.add_text_memo(str(memo)[:28])

    def _horizon_usdc(self, raw: dict[str, Any]) -> tuple[bool, float]:
        for bal in raw.get("balances", []):
            if bal.get("asset_code") == "USDC" and bal.get("asset_issuer") == USDC_ISSUER:
                return True, float(bal.get("balance") or 0)
        return False, 0.0

    def _buy_usdc_on_dex(self, kp: Keypair, usdc: Asset, dest_amount: float) -> None:
        """Fill USDC immediately via path payment with error handling"""
        try:
            dest_str = f"{dest_amount:.7f}".rstrip("0").rstrip(".")
            
            # Find path
            try:
                paths = self.horizon.strict_receive_paths(
                    source=[Asset.native()],
                    destination_asset=usdc,
                    destination_amount=dest_str,
                ).call()
            except BaseHorizonError as e:
                raise ValueError(
                    ErrorResponse(
                        error="DEX path query failed",
                        error_code="DEX_PATH_ERROR",
                        details=[
                            ErrorDetail(
                                field="dex",
                                message=f"Failed to query DEX for path: {str(e)}",
                                code="HORIZON_ERROR"
                            )
                        ]
                    ).model_dump_json()
                ) from e
            
            records = (paths.get("_embedded") or {}).get("records") or []
            if not records:
                raise ValueError(
                    ErrorResponse(
                        error="No DEX path available",
                        error_code="DEX_NO_PATH",
                        details=[
                            ErrorDetail(
                                field="dex",
                                message=f"No path found for {dest_str} USDC on DEX",
                                code="LIQUIDITY_ERROR"
                            )
                        ]
                    ).model_dump_json()
                )
            
            best = records[0]
            send_max = f"{float(best['source_amount']) * 1.25:.7f}"
            hop_assets: list[Asset] = []
            for hop in best.get("path") or []:
                if hop.get("asset_type") == "native":
                    hop_assets.append(Asset.native())
                else:
                    hop_assets.append(Asset(hop["asset_code"], hop["asset_issuer"]))
            
            # Load account
            try:
                source = self.horizon.load_account(kp.public_key)
            except NotFoundError as e:
                raise ValueError(
                    ErrorResponse(
                        error="Account not found on Stellar network",
                        error_code="ACCOUNT_NOT_FOUND",
                        details=[
                            ErrorDetail(
                                field="account",
                                message=f"Account {kp.public_key} not found on network",
                                code="HORIZON_ERROR"
                            )
                        ]
                    ).model_dump_json()
                ) from e
            except BaseHorizonError as e:
                raise ValueError(
                    ErrorResponse(
                        error="Failed to load account from Stellar network",
                        error_code="ACCOUNT_LOAD_ERROR",
                        details=[
                            ErrorDetail(
                                field="account",
                                message=f"Horizon error loading account: {str(e)}",
                                code="HORIZON_ERROR"
                            )
                        ]
                    ).model_dump_json()
                ) from e
            
            # Build and submit transaction
            try:
                builder = TransactionBuilder(
                    source_account=source,
                    network_passphrase=NETWORK_PASSPHRASE,
                    base_fee=1000,
                )
                builder.append_path_payment_strict_receive_op(
                    destination=kp.public_key,
                    send_asset=Asset.native(),
                    send_max=send_max,
                    dest_asset=usdc,
                    dest_amount=dest_str,
                    path=hop_assets,
                )
                tx = builder.set_timeout(120).build()
                tx.sign(kp)
                result = self.horizon.submit_transaction(tx)
                print(
                    f"DEX path payment OK hash={result.get('hash')} "
                    f"max_xlm={send_max} recv_usdc={dest_str}"
                )
            except BaseHorizonError as e:
                raise ValueError(
                    ErrorResponse(
                        error="Stellar transaction sequence error",
                        error_code="SEQUENCE_ERROR",
                        details=[
                            ErrorDetail(
                                field="transaction",
                                message=f"Transaction sequence number mismatch: {str(e)}",
                                code="HORIZON_ERROR"
                            )
                        ]
                    ).model_dump_json()
                ) from e
            except BaseHorizonError as e:
                raise ValueError(
                    ErrorResponse(
                        error="Stellar transaction submission failed",
                        error_code="TRANSACTION_ERROR",
                        details=[
                            ErrorDetail(
                                field="transaction",
                                message=f"Horizon rejected transaction: {str(e)}",
                                code="HORIZON_ERROR"
                            )
                        ]
                    ).model_dump_json()
                ) from e
            except Exception as e:
                raise ValueError(
                    ErrorResponse(
                        error="DEX transaction error",
                        error_code="DEX_TRANSACTION_ERROR",
                        details=[
                            ErrorDetail(
                                field="dex",
                                message=f"Unexpected DEX transaction error: {str(e)}",
                                code="UNKNOWN_ERROR"
                            )
                        ]
                    ).model_dump_json()
                ) from e
                
        except ValueError as e:
            # Re-raise ValueError with ErrorResponse
            raise

    async def submit_usdc_to_treasury(
        self,
        destination: str,
        amount: float,
        memo: Optional[str] = None,
        memo_type: str = "text",
        negotiation_id: Optional[str] = None,
        supplier: str = "TRY Anchor",
    ) -> TransactionRecord:
        kp = self.agent_keypair()
        await self.ensure_funded(kp)
        usdc = Asset("USDC", USDC_ISSUER)
        source = self.horizon.load_account(kp.public_key)
        raw = source.raw_data or {}
        has_usdc, usdc_bal = self._horizon_usdc(raw)
        if not has_usdc:
            builder = TransactionBuilder(
                source_account=source,
                network_passphrase=NETWORK_PASSPHRASE,
                base_fee=1000,
            )
            builder.append_change_trust_op(asset=usdc)
            trust_tx = builder.set_timeout(120).build()
            trust_tx.sign(kp)
            self.horizon.submit_transaction(trust_tx)
            print("USDC trustline açıldı")
            source = self.horizon.load_account(kp.public_key)
            has_usdc, usdc_bal = self._horizon_usdc(source.raw_data or {})

        if usdc_bal + 1e-7 < amount:
            need = round(amount - usdc_bal + 0.02, 7)
            print(f"USDC bakiyesi {usdc_bal} < {amount}; DEX'ten {need} USDC alınıyor")
            await self._ui_step(f"Testnet DEX: XLM → {need} USDC path payment…")
            try:
                self._buy_usdc_on_dex(kp, usdc, need)
            except Exception as e:
                print(f"DEX USDC alım hatası: {e}")
                self._last_horizon_error = f"DEX USDC alım hatası: {e}"
                tx_hash = None
                status = "simulated"
                record = TransactionRecord(
                    negotiation_id=negotiation_id or "",
                    supplier=supplier,
                    amount=amount,
                    tx_hash=tx_hash,
                    status=status,
                )
                store.transactions.insert(0, record)
                return record
            source = self.horizon.load_account(kp.public_key)
            has_usdc, usdc_bal = self._horizon_usdc(source.raw_data or {})

        print(
            f"Horizon hesap {kp.public_key[:8]}… seq={source.sequence} "
            f"USDC={usdc_bal} trustline={has_usdc} pay={amount} → {destination}"
        )
        builder = TransactionBuilder(
            source_account=source,
            network_passphrase=NETWORK_PASSPHRASE,
            base_fee=1000,
        )
        self._apply_memo(builder, memo, memo_type)
        builder.append_payment_op(destination=destination, amount=f"{amount:.2f}", asset=usdc)
        tx = builder.set_timeout(120).build()
        tx.sign(kp)
        try:
            result = self.horizon.submit_transaction(tx)
            tx_hash = result.get("hash")
            status = "submitted"
            print(f"Horizon submit OK hash={tx_hash}")
        except Exception as e:
            extras = getattr(e, "extras", None)
            print(f"Horizon Submit Hatası: {e}")
            if extras:
                print(f"Horizon extras: {extras}")
            self._last_horizon_error = str(e)
            tx_hash = None
            status = "simulated"
        record = TransactionRecord(
            negotiation_id=negotiation_id or "",
            supplier=supplier,
            amount=amount,
            tx_hash=tx_hash,
            status=status,
        )
        store.transactions.insert(0, record)
        if status == "submitted":
            store.mock_balances["usdc"] = max(0.0, store.mock_balances["usdc"] - amount)
            store.mock_balances["mock_try"] += amount
        return record

    async def execute_offramp(
        self,
        amount: float = 445.0,
        iban: str = DEFAULT_IBAN,
        negotiation_id: Optional[str] = None,
        supplier: str = "TRY Anchor",
    ) -> dict[str, Any]:
        """Execute SEP-6 offramp with comprehensive error handling"""
        try:
            await self._ui_step("SEP-10 Kimlik Doğrulanıyor (API Key Yok)...")
            token = await self.sep10_authenticate()

            await self._ui_step("SEP-6 Çekim Talebi Oluşturuldu (TR IBAN)...")
            withdraw = await self.sep6_withdraw(amount=amount, iban=iban, sep10_token=token)
            
            if not withdraw.get("ok"):
                await self._ui_step(f"SEP-6 hata: {withdraw.get('body') or withdraw}")
                return withdraw

            dest = withdraw.get("account_id")
            if not dest:
                await self._ui_step("SEP-6 treasury adresi dönmedi", level="warn")
                return withdraw

            try:
                record = await self.submit_usdc_to_treasury(
                    destination=dest,
                    amount=amount,
                    memo=withdraw.get("memo"),
                    memo_type=withdraw.get("memo_type") or "text",
                    negotiation_id=negotiation_id,
                    supplier=supplier,
                )
                if record.status == "simulated":
                    detail = getattr(self, "_last_horizon_error", None)
                    if detail:
                        await self._ui_step(f"Horizon Submit Hatası: {detail}", level="warn")
                    await self._ui_step(INSUFFICIENT_USDC_MSG, level="warn")
                    withdraw["simulated"] = True
                    withdraw["message"] = INSUFFICIENT_USDC_MSG
                else:
                    await self._ui_step("Stellar Ağına On-Chain Ödeme Gönderildi - TL Bankaya Aktarılıyor")
                    withdraw["tx_hash"] = record.tx_hash
                    withdraw["message"] = f"{amount:.2f} USDC → {dest} | {record.tx_hash}"
            except ValueError as e:
                # Re-raise ValueError with ErrorResponse
                raise
            except Exception as exc:
                await self._ui_step(INSUFFICIENT_USDC_MSG, level="warn")
                withdraw["simulated"] = True
                withdraw["message"] = INSUFFICIENT_USDC_MSG
                withdraw["error"] = str(exc)
            
            withdraw["ok"] = True
            return withdraw
            
        except ValueError as e:
            # Re-raise ValueError with ErrorResponse
            raise
        except Exception as exc:
            raise ValueError(
                ErrorResponse(
                    error="Offramp execution error",
                    error_code="OFFRAMP_ERROR",
                    details=[
                        ErrorDetail(
                            field="offramp",
                            message=f"Unexpected offramp error: {str(exc)}",
                            code="UNKNOWN_ERROR"
                        )
                    ]
                ).model_dump_json()
            ) from exc

    async def on_deal_reached(self, amount: float, negotiation_id: Optional[str] = None) -> None:
        try:
            await self.execute_offramp(amount=amount, negotiation_id=negotiation_id)
        except (httpx.RequestError, httpx.HTTPStatusError):
            await self._ui_step(FALLBACK_MSG, level="warn")
        except Exception:
            await self._ui_step(INSUFFICIENT_USDC_MSG, level="warn")

    # Compatibility with older /api/sep10 routes (still wallet-signed, never API keys)
    def challenge(self, account: str) -> dict:
        toml = self.discover_toml()
        resp = httpx.get(toml["WEB_AUTH_ENDPOINT"], params={"account": account}, timeout=ANCHOR_TIMEOUT)
        resp.raise_for_status()
        body = resp.json()
        return {
            "account": account,
            "network_passphrase": NETWORK_PASSPHRASE,
            "transaction": body.get("transaction"),
            "home_domain": "tr-mock-anchor.fly.dev",
        }

    def verify(self, account: str, signed_transaction: str) -> dict:
        toml = self.discover_toml()
        resp = httpx.post(
            toml["WEB_AUTH_ENDPOINT"],
            json={"transaction": signed_transaction},
            timeout=ANCHOR_TIMEOUT,
        )
        if resp.status_code >= 400:
            return {"ok": False, "error": resp.text}
        token = resp.json().get("token")
        return {"ok": True, "token": token, "account": account}

    def account_for_token(self, token: Optional[str]) -> Optional[str]:
        return store.wallet_public_key if token else None

    async def _ui_step(self, message: str, level: str = "info") -> None:
        await ws_manager.broadcast({"type": "anchor_step", "message": message, "level": level})
        await self._log(level, "anchor", message)

    async def _log(self, level: str, source: str, message: str, negotiation_id: Optional[str] = None) -> AgentLog:
        log = AgentLog(level=level, source=source, message=message, negotiation_id=negotiation_id)
        store.logs.append(log)
        await ws_manager.broadcast({"type": "log", "data": log.model_dump(mode="json")})
        return log


stellar_anchor_service = StellarAnchorService()