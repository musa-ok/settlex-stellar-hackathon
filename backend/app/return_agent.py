from __future__ import annotations

import asyncio
import re

from .llm_negotiation import append_log, llm
from .models import Invoice, Negotiation, NegotiationStatus
from .stellar_anchor import DEFAULT_IBAN, stellar_anchor_service
from .store import store
from .websocket_manager import ws_manager

CUSTOMER_IBAN = DEFAULT_IBAN


def calculate_coupon_rate(order_total: float) -> float:
    if order_total <= 200:
        return 0.15
    elif order_total >= 10000:
        return 0.05
    else:
        ratio = (order_total - 200) / (10000 - 200)
        rate = 0.15 - (ratio * (0.15 - 0.05))
        return round(rate, 2)


def build_brand_system(order_total: float, lang: str = "tr") -> str:
    coupon_rate = calculate_coupon_rate(order_total)
    coupon_percent = int(coupon_rate * 100)

    prompt = (
        "Sen şirketimizin B2C müşteri memnuniyetinden ve finansal kârlılığından sorumlu profesyonel yapay zeka temsilcisisin. "
        "Karşındaki müşterinin talebini (tam iade, kısmi iade, ürünün bir kısmı vs.) çok iyi oku ve anla. "
        "Görevlerin: "
        "- Şirket kasasından on-chain nakit çıkışını en aza indirmek için müşteriyi içeride tutacak mağaza kredisi ve ek kupon fırsatları sunarak pazarlığa başla. "
        f"- Teşvik kuponu sunarken KESİNLİKLE %{coupon_percent} oranını kullan (bu oran sipariş tutarına göre sistem tarafından önceden hesaplanmıştır, "
        f"kendi kafandan farklı bir oran uydurma, değiştirme, yuvarlama yapma. Sabit değer: %{coupon_percent}). "
        "- Müşterinin mesajında birden fazla istek varsa (örn: 'şu kadarını nakit verin, kalanı için anlaşalım'), teklifini tüm bu istekleri eksiksiz kapsayacak mantıklı bir paket olarak sun. Hiçbir tutarı veya ürünü havada bırakma. "
        "- Müşteri nakit iadede ısrarcıysa süreci uzatma ve SADECE müşterinin nakit olarak talep ettiği tutarı onayla, ancak iade edilecek bedele karşılık gelen kusurlu/istenmeyen ürünlerin mağazaya kargolanmasını kibar bir dille şart koş. "
        "- Robotik kalıplardan kaçın, durumu analiz eden, insani ve çözüm odaklı bir ticaret uzmanı gibi davran. "
        "- Karma İade (Split Refund) Kuralı: Müşteri toplam sipariş tutarının sadece bir kısmını nakit istiyorsa (Örn: 1000 TL'lik siparişte 50 TL nakit), ASLA ürünü fiziksel olarak parçalara bölüp 'sağlam kısım sizde kalsın' gibi saçma şeyler söyleme! Ürünün TAMAMININ kargoyla iade edilmesini KESİN ŞART KOŞ. Anlaşmayı şu net formatta onayla: 'Ürünün tamamını tarafımıza kargolamanız şartıyla belirttiğiniz [X] TL nakit iadenizi (SEP-6) onaylıyor, siparişin geriye kalan [TOPLAM - X] TL bakiyesini ise anında hesabınıza mağaza kredisi olarak tanımlıyorum.' "
        "- NAKİT TUTAR KURALI (ÇOK ÖNEMLİ): Ödenecek nakit tutar KESİNLİKLE müşterinin O TURDA/O MESAJDA NAKİT OLARAK TALEP ETTİĞİ TUTARLA birebir aynı olmalıdır. "
        "  * Müşteri tam iade istiyorsa (ör. '1000 TL'nin tamamını nakit istiyorum') → nakit tutar = sipariş toplamı. "
        "  * Müşteri kısmi/karma iade istiyorsa (ör. '1000 TL'lik siparişten sadece 50 TL nakit istiyorum') → nakit tutar = SADECE o 50 TL. Kalan kısım ASLA nakit olarak ödenmez, mağaza kredisi olarak tanımlanır. "
        "  * Sipariş toplamını nakit tutar sanıp müşterinin belirtmediği bir rakamı ödemeye ASLA karar verme. "
        "- Asla tutarı ikiye katlama, kafandan para ekleme veya toplama/çıkarma hatası yapma. Hesabı anlık ve müşterinin son mesajındaki rakamlara göre yap. "
        "- Anlaşma sağlandığında işlemi sonlandır. "
        "price alanına o turdaki NAKİT teklif tutarını yaz (mağaza kredisi tutarını price alanına yazma, price sadece nakit kısmı temsil eder)."
    )
    if lang == "en":
        prompt += "\nCRITICAL INSTRUCTION: You are negotiating with an English-speaking user/agent. You MUST write all your conversational responses, negotiations, and offers strictly in English. Do not use Turkish."
        prompt += "\nCRITICAL: When you accept an offer, you MUST conclude the negotiation strictly with this exact phrase: Accepted — full cash refund, shipping the item. Deal. Do not use any Turkish words."
    else:
        prompt += "\nTüm pazarlık ve iletişimini Türkçe yap."
        prompt += "\nAnlaşma sağlandığında KESİNLİKLE şu cümleyle bitir: Kabul — tam nakit iade, ürünü kargoluyorum. Deal."
    return prompt


def customer_system(b2c_input: str, lang: str = "tr") -> str:
    prompt = (
        "Sen e-ticaret sitemizden alışveriş yapmış ve iade/değişim talebinde bulunan gerçekçi bir müşterisin. "
        f"İade talebin ve niyetin tam olarak şu: '{b2c_input}' "
        "Görevlerin: "
        "- İlk mesajında talebini ve niyetini doğal bir şekilde ilet. "
        "- Karma İade (Split Refund) Mantığı: Eğer {b2c_input} metninde toplam sipariş tutarından daha düşük bir nakit talebi varsa (Örn: 1000 TL'lik siparişin 50 TL'sini nakit istemek), ürünü parçalayarak iade ediyormuş gibi mantıksız cümleler kurma. Niyetini ilk mesajda net bir 'Karma İade' olarak belirt ve NAKİT TALEBİNİN RAKAMINI AÇIKÇA SÖYLE: 'Siparişimdeki ürünün TAMAMINI iade etmek istiyorum, ancak toplam tutarın sadece [X] TL'sinin nakit olarak ödenmesini, kalan [TOPLAM - X] TL'nin ise mağaza kredisi olarak değerlendirilmesini talep ediyorum.' "
        "- MİNİMUM NAKİT KURALI: Sen bu görüşme boyunca nakit olarak asgari [X] TL talep ediyorsun. Bu senin taban rakamın; müzakere boyunca aklından çıkarma. "
        "- Satıcıdan gelen karşı teklifleri (mağaza kredisi, kupon, kısmi nakit vb.) cümlenin bütününe bakarak değerlendir. "
        "- 'Esnek' olduğunu belirtsen bile (kalan bakiye için 'değerlendirmeye açığım' gibi), bu esneklik SADECE mağaza kredisi/kupon kısmı için geçerlidir. Nakit talep ettiğin [X] TL rakamının ALTINDA bir teklifi ASLA kabul etme. "
        "- Kabul etmeden önce kontrol et: satıcının teklif ettiği nakit tutar, senin talep ettiğin [X] TL'ye eşit mi? Satıcı bunun yerine sipariş toplamının tamamını nakit olarak teklif ederse (senin talebini aşan bir teklif), bunu KABUL ETME — nakit talebinin sadece [X] TL olduğunu, kalanının mağaza kredisi olması gerektiğini nazikçe hatırlat ve orijinal talebini tekrarla. "
        "- Satıcı senin talebinin bir kısmını (örneğin geri kalan bakiye veya diğer ürünler) eksik bırakırsa, eksik kalan kısmı hatırlatıp müzakereyi toparla. "
        "- Anlaşma sağlandığında (nakit tutar = senin talebinle birebir aynıysa) 'Kabul - Deal' de. "
        "price alanına o turda talep ettiğin veya kabul ettiğin NAKİT tutarını yaz (kredi kabulünde 0)."
    )
    if lang == "en":
        prompt += "\nCRITICAL INSTRUCTION: You are negotiating with an English-speaking user/agent. You MUST write all your conversational responses, negotiations, and offers strictly in English. Do not use Turkish."
        prompt += "\nCRITICAL: When you accept an offer, you MUST conclude the negotiation strictly with this exact phrase: Accepted — full cash refund, shipping the item. Deal. Do not use any Turkish words."
    else:
        prompt += "\nTüm pazarlık ve iletişimini Türkçe yap."
        prompt += "\nAnlaşma sağlandığında KESİNLİKLE şu cümleyle bitir: Kabul — tam nakit iade, ürünü kargoluyorum. Deal."
    return prompt


def parse_return_request(text: str) -> tuple[str, float]:
    raw = (text or "").strip()
    amount_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:TL|₺)?", raw, re.IGNORECASE)
    amount = float(amount_match.group(1).replace(",", ".")) if amount_match else 0.0
    product = re.sub(r"\d+(?:[.,]\d+)?\s*(?:TL|₺)?", "", raw, flags=re.IGNORECASE)
    product = re.sub(r"[,:;.\-–]+$", "", product).strip(" ,") or "ürün"
    return product, amount


class ReturnAgentService:
    """B2C iade pazarlığı: mağaza ajanı ↔ müşteri simülasyonu → SEP-6."""

    async def start_return(self, text: str | None = None, lang: str = "tr") -> Negotiation:
        b2c_input = (text or "").strip()
        product, list_price = parse_return_request(b2c_input)
        invoice = Invoice(
            supplier="E-ticaret mağazası",
            product=product,
            quantity=1,
            amount=list_price,
        )
        store.invoices[invoice.id] = invoice
        neg = Negotiation(
            invoice_id=invoice.id,
            supplier="E-ticaret mağazası",
            product=product,
            quantity=1,
            initial_amount=list_price,
            current_amount=list_price,
            status=NegotiationStatus.NEGOTIATING,
        )
        store.negotiations[neg.id] = neg
        try:
            await self._loop(neg, b2c_input, list_price, lang=lang)
        except Exception as exc:
            await append_log(
                neg,
                "seller",
                list_price,
                f"İade ajanı hatası: {exc}",
                "negotiating",
                0,
            )
        return neg

    async def _loop(self, neg: Negotiation, b2c_input: str, list_price: float, lang: str = "tr") -> None:
        cust_sys = customer_system(b2c_input, lang=lang)
        brand_sys = build_brand_system(list_price, lang=lang)
        credit = round(list_price, 2) if list_price else 0.0
        full_cash = round(list_price, 2) if list_price else 0.0

        customer = await llm.complete(
            cust_sys,
            f"Şu talebim için iade istiyorum: {b2c_input}. "
            "Nakit iade istediğini söyle, iyi teklife açık olduğunu ima et. status=negotiating.",
        )
        await append_log(neg, "buyer", customer["price"], customer["message"], "negotiating", 1)
        await asyncio.sleep(1)

        brand = await llm.complete(
            brand_sys,
            f"Müşteri mesajı: {customer['message']}. "
            f"Ham talep metni: {b2c_input}. "
            "Talep edilen asıl tutarı analiz et, %100 mağaza kredisini ve sistemin belirlediği kupon oranını teklif et. "
            "Henüz anlaşma yok. status=negotiating.",
        )
        await append_log(neg, "seller", brand["price"], brand["message"], "negotiating", 2)
        await asyncio.sleep(1)

        if brand.get("status") == "deal" and self._is_store_credit(brand, credit):
            await self._close_store_credit(neg, float(brand["price"] or credit))
            return

        customer2 = await llm.complete(
            cust_sys,
            f"Markamız şu cevabı verdi: {brand['message']} (price={brand['price']}). "
            "Nakit iadede ısrar et. status=negotiating.",
        )
        if customer2.get("status") == "deal":
            await append_log(
                neg, "buyer", customer2["price"], customer2["message"], "deal", 3
            )
            if self._is_store_credit(customer2, credit):
                await self._close_store_credit(neg, credit)
            else:
                cash = self._cash_amount(customer2, credit) or full_cash
                await self._close_cash(neg, cash)
            return

        await append_log(
            neg, "buyer", customer2["price"], customer2["message"], "negotiating", 3
        )
        await asyncio.sleep(1)

        brand2 = await llm.complete(
            brand_sys,
            f"Müşteri nakit iadede ısrar ediyor: {customer2['message']}. "
            f"Ham talep: {b2c_input}. "
            "Müşterinin nakit olarak talep ettiği tutarı (toplam sipariş tutarı değil, sadece nakit istediği kısmı) "
            "SEP-6 ile onayla, ürünün tamamının geri gönderilmesi şartıyla, ve status=deal yaz. "
            f"KESİNLİKLE şu cümleyle bitir: {'Accepted — full cash refund, shipping the item. Deal.' if lang == 'en' else 'Kabul — tam nakit iade, ürünü kargoluyorum. Deal.'}",
        )
        brand2["status"] = "deal"
        cash = float(brand2.get("price") or 0) or full_cash
        brand2["price"] = cash
        await append_log(neg, "seller", brand2["price"], brand2["message"], "deal", 4)
        await append_log(
            neg,
            "buyer",
            cash,
            "Accepted — full cash refund, shipping the item. Deal." if lang == "en" else "Kabul — tam nakit iade, ürünü kargoluyorum. Deal.",
            "deal",
            4,
        )
        await self._close_cash(neg, cash)

    def _is_store_credit(self, offer: dict, credit: float) -> bool:
        message = str(offer.get("message", "")).lower()
        if "kredi" in message or "paket" in message:
            return True
        price = float(offer.get("price") or 0)
        if price <= 0:
            return True
        return False

    def _cash_amount(self, offer: dict, credit: float) -> float:
        price = float(offer.get("price") or 0)
        if price <= 0:
            return 0.0
        if self._is_store_credit(offer, credit):
            return 0.0
        return price

    async def _close_store_credit(self, neg: Negotiation, credit: float) -> None:
        neg.agreed_amount = 0.0
        neg.current_amount = 0.0
        neg.status = NegotiationStatus.AGREED
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
        await ws_manager.broadcast(
            {
                "type": "anchor_step",
                "message": (
                    f"Mutabakat: {credit:.0f} TL mağaza kredisi — nakit SEP-6 çıkışı yok"
                    if credit
                    else "Mutabakat: mağaza kredisi — nakit SEP-6 çıkışı yok"
                ),
                "level": "info",
            }
        )
        neg.status = NegotiationStatus.PAID
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})

    async def _close_cash(self, neg: Negotiation, amount: float) -> None:
        neg.agreed_amount = amount
        neg.current_amount = amount
        neg.status = NegotiationStatus.AGREED
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})
        await stellar_anchor_service.execute_offramp(
            amount=amount,
            iban=CUSTOMER_IBAN,
            negotiation_id=neg.id,
            supplier="iade",
        )
        neg.status = NegotiationStatus.PAID
        store.negotiations[neg.id] = neg
        await ws_manager.broadcast({"type": "negotiation", "data": neg.model_dump()})


return_agent = ReturnAgentService()
