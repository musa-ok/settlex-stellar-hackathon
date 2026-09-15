#!/usr/bin/env python3
"""Open USDC trustline and buy USDC on Stellar testnet DEX via path payment."""

from __future__ import annotations

import sys
from pathlib import Path

from stellar_sdk import Asset, Keypair, Network, Server, TransactionBuilder

HORIZON_URL = "https://horizon-testnet.stellar.org"
NETWORK_PASSPHRASE = Network.TESTNET_NETWORK_PASSPHRASE
USDC_ISSUER = "GBBD47IF6LWK7P7MDEVSCWR7DPUWV3NY3DTQEVFL4NAT4AQH3ZLLFLA5"
BUY_AMOUNT = "500"
SECRET_PATH = Path(__file__).resolve().parent / ".data" / "agent_secret"


def load_keypair() -> Keypair:
    if not SECRET_PATH.exists():
        raise SystemExit(f"Secret yok: {SECRET_PATH} — önce uygulamayı bir kez çalıştırın.")
    secret = SECRET_PATH.read_text().strip()
    if not secret:
        raise SystemExit("agent_secret boş")
    return Keypair.from_secret(secret)


def has_usdc_trust(account: dict) -> bool:
    for bal in account.get("balances", []):
        if bal.get("asset_code") == "USDC" and bal.get("asset_issuer") == USDC_ISSUER:
            return True
    return False


def usdc_balance(account: dict) -> float:
    for bal in account.get("balances", []):
        if bal.get("asset_code") == "USDC" and bal.get("asset_issuer") == USDC_ISSUER:
            return float(bal.get("balance") or 0)
    return 0.0


def submit(server: Server, kp: Keypair, builder: TransactionBuilder) -> str:
    tx = builder.set_timeout(120).build()
    tx.sign(kp)
    result = server.submit_transaction(tx)
    return result["hash"]


def buy_usdc(server: Server, kp: Keypair, usdc: Asset, dest_amount: str) -> str:
    paths = server.strict_receive_paths(
        source=[Asset.native()],
        destination_asset=usdc,
        destination_amount=dest_amount,
    ).call()
    records = (paths.get("_embedded") or {}).get("records") or []
    if not records:
        raise RuntimeError(f"DEX path yok ({dest_amount} USDC)")
    best = records[0]
    send_max = f"{float(best['source_amount']) * 1.25:.7f}"
    hops: list[Asset] = []
    for hop in best.get("path") or []:
        if hop.get("asset_type") == "native":
            hops.append(Asset.native())
        else:
            hops.append(Asset(hop["asset_code"], hop["asset_issuer"]))
    print(f"Path: max {send_max} XLM → {dest_amount} USDC hops={len(hops)}")
    source = server.load_account(kp.public_key)
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
        dest_amount=dest_amount,
        path=hops,
    )
    return submit(server, kp, builder)


def main() -> None:
    kp = load_keypair()
    print(f"Hesap: {kp.public_key}")
    server = Server(horizon_url=HORIZON_URL)
    usdc = Asset("USDC", USDC_ISSUER)
    account = server.accounts().account_id(kp.public_key).call()

    source = server.load_account(kp.public_key)
    if not has_usdc_trust(account):
        print("USDC trustline açılıyor…")
        trust_builder = TransactionBuilder(
            source_account=source,
            network_passphrase=NETWORK_PASSPHRASE,
            base_fee=1000,
        )
        trust_builder.append_change_trust_op(asset=usdc)
        trust_hash = submit(server, kp, trust_builder)
        print(f"Trustline tx: {trust_hash}")
    else:
        print("USDC trustline zaten var.")

    print(f"{BUY_AMOUNT} USDC path payment (XLM → USDC)…")
    offer_hash = buy_usdc(server, kp, usdc, BUY_AMOUNT)
    print(f"DEX path payment tx: {offer_hash}")
    account = server.accounts().account_id(kp.public_key).call()
    print(f"Yeni USDC bakiyesi: {usdc_balance(account)}")
    print("Tamam.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        raise SystemExit(1)
