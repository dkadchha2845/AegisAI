"""
B. Scam script template matching.

The spec: "Rather than exact keyword matching, sentence embeddings allow
recognition of paraphrased scam scripts."

That is the requirement this module implements, and the reason it matters is
concrete. A keyword list catches "arrest warrant issue ho chuka hai" and misses
"court se order aaya hai aapke naam par" — same threat, same function in the
script, no shared keyword. Scammers vary surface wording constantly; the
*template* underneath is what stays fixed, because it is what works.

Two backends, one interface
---------------------------
    dense    sentence-transformers cosine similarity. Catches paraphrase.
    lexical  weighted token-overlap with IDF. Catches restatement.

The lexical backend is not a stub. It uses the same corpus statistics the BM25
retriever in `rag/store.py` is built on, and on this data — short utterances,
heavy domain vocabulary, code-mixed — token overlap recovers a large fraction
of what embeddings find. What it genuinely cannot do is match across a full
lexical substitution, which is exactly what the degradation tag communicates.

Each template carries its scam type, so a match is simultaneously evidence of
*that this is a scam* and of *which scam it is* — the two outputs the RSSIE
classifier needs, from one comparison.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

#: Canonical scam-script templates, grouped by the scam type they belong to.
#: Every line here is a *function* in the script rather than a memorable
#: sentence — the point is what the utterance is trying to achieve, so
#: paraphrases cluster near it in embedding space.
TEMPLATES: list[dict] = [
    # --- Digital arrest -------------------------------------------------
    {"id": "da_authority", "scam_type": "DIGITAL_ARREST", "stage": "AUTHORITY_CLAIM",
     "label": "Law-enforcement impersonation",
     "text": "Main CBI crime branch se inspector bol raha hoon, badge number note kar lijiye"},
    {"id": "da_parcel", "scam_type": "DIGITAL_ARREST", "stage": "FEAR_INDUCTION",
     "label": "Contraband parcel allegation",
     "text": "Aapke Aadhaar par ek parcel mila hai jisme drugs aur fake passport hain"},
    {"id": "da_laundering", "scam_type": "DIGITAL_ARREST", "stage": "FEAR_INDUCTION",
     "label": "Money-laundering case allegation",
     "text": "Aapke naam par money laundering ka case register ho chuka hai, non-bailable offence hai"},
    {"id": "da_warrant", "scam_type": "DIGITAL_ARREST", "stage": "FEAR_INDUCTION",
     "label": "Arrest warrant threat",
     "text": "Arrest warrant issue ho chuka hai, do ghante mein police aapke ghar aayegi"},
    {"id": "da_digital_arrest", "scam_type": "DIGITAL_ARREST", "stage": "ISOLATION",
     "label": "Digital arrest instruction",
     "text": "Aap digital arrest par hain, video call on rakhiye aur kamre se bahar mat jaiye"},
    {"id": "da_secrecy", "scam_type": "DIGITAL_ARREST", "stage": "ISOLATION",
     "label": "Confidentiality demand",
     "text": "Ye investigation confidential hai, kisi ko bataya to unko bhi accused bana denge"},
    {"id": "da_no_disconnect", "scam_type": "DIGITAL_ARREST", "stage": "ISOLATION",
     "label": "Call-disconnection prohibition",
     "text": "Call disconnect mat kariye warna case aur serious ho jayega"},
    {"id": "da_rbi_account", "scam_type": "DIGITAL_ARREST", "stage": "PAYMENT_SETUP",
     "label": "RBI supervised-account transfer",
     "text": "RBI ke supervised verification account mein funds transfer kariye, audit ke baad wapas mil jayega"},

    # --- Courier / customs ----------------------------------------------
    {"id": "cp_parcel_seized", "scam_type": "COURIER_PARCEL", "stage": "FEAR_INDUCTION",
     "label": "Seized courier parcel",
     "text": "FedEx se bol raha hoon, aapke naam ka parcel customs ne seize kar liya hai"},
    {"id": "cp_customs_duty", "scam_type": "COURIER_PARCEL", "stage": "PAYMENT_SETUP",
     "label": "Customs clearance fee",
     "text": "Parcel release karne ke liye customs duty aur clearance charge abhi pay karna hoga"},

    # --- KYC expiry -------------------------------------------------------
    {"id": "kyc_expired", "scam_type": "KYC_EXPIRY", "stage": "FEAR_INDUCTION",
     "label": "KYC expiry account freeze",
     "text": "Aapki KYC expire ho gayi hai, aaj shaam tak account permanently freeze ho jayega"},
    {"id": "kyc_otp", "scam_type": "KYC_EXPIRY", "stage": "VERIFICATION_DEMAND",
     "label": "KYC re-verification OTP demand",
     "text": "Registered mobile par OTP aaya hoga, verification ke liye wo number bataiye"},

    # --- Refund / overpayment --------------------------------------------
    {"id": "ro_excess", "scam_type": "REFUND_OVERPAYMENT", "stage": "PAYMENT_SETUP",
     "label": "Overpaid-refund return demand",
     "text": "Aapke account mein galti se zyada refund chala gaya hai, extra amount wapas bhejiye"},
    {"id": "ro_pin_receive", "scam_type": "REFUND_OVERPAYMENT", "stage": "PAYMENT_EXECUTION",
     "label": "PIN required to receive money",
     "text": "Refund receive karne ke liye ye QR scan kariye aur apna UPI PIN daaliye"},

    # --- SIM / TRAI -------------------------------------------------------
    {"id": "trai_disconnect", "scam_type": "SIM_TRAI_DISCONNECTION", "stage": "FEAR_INDUCTION",
     "label": "TRAI number disconnection threat",
     "text": "TRAI se bol raha hoon, aapka number illegal activity mein use hua hai, do ghante mein band ho jayega"},

    # --- Utility ----------------------------------------------------------
    {"id": "util_disconnect", "scam_type": "UTILITY_DISCONNECTION", "stage": "FEAR_INDUCTION",
     "label": "Electricity disconnection threat",
     "text": "Aapka bijli bill pending hai, aaj raat connection kaat diya jayega"},

    # --- Investment / crypto ---------------------------------------------
    {"id": "inv_returns", "scam_type": "INVESTMENT_RETURNS", "stage": "PAYMENT_SETUP",
     "label": "Guaranteed-returns investment",
     "text": "Hamare private trading group mein guaranteed return milta hai, pehle deposit kariye"},
    {"id": "inv_withdraw_fee", "scam_type": "INVESTMENT_RETURNS", "stage": "PAYMENT_SETUP",
     "label": "Withdrawal-unlock deposit",
     "text": "Profit withdraw karne ke liye pehle tax deposit karna padega"},

    # --- Loan app harassment ---------------------------------------------
    {"id": "loan_threat", "scam_type": "LOAN_APP_HARASSMENT", "stage": "FEAR_INDUCTION",
     "label": "Contact-list blackmail",
     "text": "Paisa nahi diya to aapke contacts ko aapki photos bhej denge"},

    # --- Job offer --------------------------------------------------------
    {"id": "job_fee", "scam_type": "JOB_OFFER_FEE", "stage": "PAYMENT_SETUP",
     "label": "Job registration fee",
     "text": "Work from home job ke liye registration aur training kit fee jama karni hogi"},

    # --- Lottery ----------------------------------------------------------
    {"id": "lot_prize", "scam_type": "LOTTERY_PRIZE", "stage": "PAYMENT_SETUP",
     "label": "Prize-release tax demand",
     "text": "Aapne lottery jeeti hai, prize release karne ke liye pehle tax bhariye"},

    # --- Tech support -----------------------------------------------------
    {"id": "tech_remote", "scam_type": "TECH_SUPPORT_REMOTE", "stage": "VERIFICATION_DEMAND",
     "label": "Remote-access installation",
     "text": "Aapka device hack ho gaya hai, ye AnyDesk app install kijiye main theek kar deta hoon"},

    # --- Generic credential extraction (crosses scam types) --------------
    {"id": "gen_otp", "scam_type": "UNKNOWN", "stage": "VERIFICATION_DEMAND",
     "label": "OTP extraction",
     "text": "Verification ke liye aapke phone par aaya hua OTP number bataiye"},
    {"id": "gen_aadhaar", "scam_type": "UNKNOWN", "stage": "VERIFICATION_DEMAND",
     "label": "Aadhaar / PAN extraction",
     "text": "Apna Aadhaar number aur PAN card details verification ke liye bataiye"},
    {"id": "gen_balance", "scam_type": "UNKNOWN", "stage": "VERIFICATION_DEMAND",
     "label": "Account balance probe",
     "text": "Aapke account mein kitna balance hai, poora amount batana zaroori hai"},
]

#: Below this a match is noise. Tuned against the benign half of the corpus:
#: legitimate bank calls share heavy vocabulary with these templates ("account",
#: "verification", "KYC"), and a lower bar fires on every one of them.
DENSE_FLOOR = 0.55
LEXICAL_FLOOR = 0.42

_TOKEN = re.compile(r"[a-z0-9]+")

#: Domain words that are high-signal but common enough to be down-weighted by
#: pure IDF. Boosted so a short utterance containing one still clears the floor.
_KEY_TERMS = {
    "otp", "aadhaar", "pin", "cvv", "warrant", "arrest", "cbi", "rbi", "trai",
    "customs", "parcel", "laundering", "confidential", "disconnect", "transfer",
    "deposit", "refund", "kyc", "freeze", "digital", "escrow", "upi", "qr",
}


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


#: Advisory framing — the text *warns about* a tactic rather than performing it.
#: "Never share your OTP" contains the same vocabulary as an OTP demand and
#: scored 0.417 against the credential template, close enough to the scam floor
#: to be a coin flip. `engine/passport.py` already learned this exact lesson:
#: matching the bare credential word flagged a genuine bank reminder as
#: CRITICAL, which is the false positive that teaches users to ignore alerts.
#:
#: Suppression is unconditional rather than a score penalty. A sentence telling
#: someone not to do something is not a weaker instance of telling them to do
#: it — it is the opposite act, and scoring it as a faint scam is wrong in kind,
#: not in degree.
_CREDENTIAL_WORD = r"(otp|pin|cvv|password|passcode|account details|card number)"

_ADVISORY_FRAMING = re.compile(
    # "never share your OTP" / "hum kabhi OTP nahi maangte" — the negated verb's
    # object must be a *credential* for this to be an advisory.
    r"\b(never|do not|don'?t|kabhi nahi|kabhi mat|mat)\b[^.!?]{0,30}"
    rf"\b{_CREDENTIAL_WORD}\b"
    rf"|\b{_CREDENTIAL_WORD}\b[^.!?]{{0,30}}\b(nahi|mat|never)\b"
    r"|\b(beware|savdhan|awareness|advisory|fraud alert|safety tip)\b",
    re.I,
)

#: Third-party concealment. This is the ISOLATION tactic and is the opposite of
#: an advisory: it instructs the listener to hide the call from other people.
#:
#: It has to be checked explicitly because it shares surface form with the
#: advisory pattern — both are negated imperatives. `engine/passport.py` records
#: this exact trap: letting "kisi ko mat bataiye" suppress a genuine demand in
#: the same breath is "a failure in the dangerous direction". The object of the
#: negation is what separates them — a credential means advisory, a *person*
#: means isolation.
_THIRD_PARTY_CONCEALMENT = re.compile(
    r"\b(kisi|koi|family|ghar walo?|bete|beti|husband|wife|anyone|anybody|"
    r"nobody|no one|police|bank)\b[^.!?]{0,25}\b(mat|nahi|not|don'?t|never)\b"
    r"|\b(mat|nahi|don'?t|never)\b[^.!?]{0,25}\b(bataiye|batana|bataye|batao|tell|"
    r"inform|disclose|discuss)\b[^.!?]{0,20}\b(kisi|koi|anyone|family|ghar)\b"
    r"|\b(confidential|secret|gupt)\b"
    r"|\bdisconnect mat\b|\bcall.{0,15}mat (kariye|karo|kijiye)\b"
    r"|\bkisi ko (mat|nahi) bat\w*",
    re.I,
)


def _is_advisory(text: str) -> bool:
    """True when the text warns about a tactic instead of performing it.

    Isolation language wins outright when both fire. A message that both
    demands secrecy from family *and* mentions a credential is a scam using
    advisory-shaped grammar, not an advisory — and suppressing it would be a
    miss on the single most diagnostic stage in the arc.
    """
    if _THIRD_PARTY_CONCEALMENT.search(text):
        return False
    return bool(_ADVISORY_FRAMING.search(text))


@dataclass
class ScriptMatchOut:
    template_id: str
    label: str
    similarity: float
    matched_text: str
    scam_type: str
    stage: str


@dataclass
class TemplateResult:
    matches: list[ScriptMatchOut] = field(default_factory=list)
    backend: str = "lexical"
    degraded: list[str] = field(default_factory=list)

    @property
    def best(self) -> ScriptMatchOut | None:
        return self.matches[0] if self.matches else None

    def scam_type_votes(self) -> dict[str, float]:
        """Similarity-weighted votes per scam type.

        Weighted rather than counted because one strong match is better
        evidence than three weak ones, and an unweighted count lets a scam type
        with more templates in the library win by having more chances to fire.
        """
        votes: dict[str, float] = {}
        for match in self.matches:
            if match.scam_type == "UNKNOWN":
                continue
            votes[match.scam_type] = votes.get(match.scam_type, 0.0) + match.similarity
        return votes


class _LexicalMatcher:
    """IDF-weighted token overlap over the template set."""

    backend = "lexical"

    def __init__(self) -> None:
        self.docs = [_tokenize(t["text"]) for t in TEMPLATES]
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(set(doc))
        n = len(self.docs)
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }
        self.sets = [set(doc) for doc in self.docs]

    def _mass(self, terms) -> float:
        return sum(
            self.idf.get(term, 1.0) * (1.6 if term in _KEY_TERMS else 1.0)
            for term in terms
        )

    def similarity(self, query_tokens: set[str], index: int) -> float:
        template = self.sets[index]
        shared = query_tokens & template
        if not shared:
            return 0.0
        # Containment, not Jaccard. Jaccard divides by the union and so
        # penalises every length difference in both directions — a one-line SMS
        # that reproduces a template's entire content scored below floor purely
        # for being short, and a long transcript containing the template scored
        # below floor purely for being long. Both are the cases this is for.
        #
        # Dividing by the *smaller* mass asks the question that actually
        # matters: is one of these two texts substantially contained in the
        # other? That is what paraphrase looks like under token overlap.
        shared_mass = self._mass(shared)
        smaller = min(self._mass(query_tokens), self._mass(template))
        return shared_mass / smaller if smaller else 0.0

    def match(self, text: str, k: int) -> list[ScriptMatchOut]:
        tokens = set(_tokenize(text))
        if not tokens:
            return []
        scored = []
        for i, template in enumerate(TEMPLATES):
            score = self.similarity(tokens, i)
            if score >= LEXICAL_FLOOR:
                scored.append(
                    ScriptMatchOut(
                        template_id=template["id"],
                        label=template["label"],
                        similarity=round(min(1.0, score), 3),
                        matched_text=text[:200],
                        scam_type=template["scam_type"],
                        stage=template["stage"],
                    )
                )
        scored.sort(key=lambda m: m.similarity, reverse=True)
        return scored[:k]


class _DenseMatcher:
    """sentence-transformers cosine similarity. Constructed only if it loads."""

    backend = "dense"

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.model = SentenceTransformer(model_name)
        self.matrix = self.model.encode(
            [t["text"] for t in TEMPLATES], normalize_embeddings=True,
            show_progress_bar=False,
        )

    def match(self, text: str, k: int) -> list[ScriptMatchOut]:
        import numpy as np  # type: ignore

        query = self.model.encode([text], normalize_embeddings=True)[0]
        sims = self.matrix @ query
        out = []
        for i in np.argsort(-sims)[: k * 2]:
            score = float(sims[int(i)])
            if score < DENSE_FLOOR:
                break
            template = TEMPLATES[int(i)]
            out.append(
                ScriptMatchOut(
                    template_id=template["id"],
                    label=template["label"],
                    similarity=round(score, 3),
                    matched_text=text[:200],
                    scam_type=template["scam_type"],
                    stage=template["stage"],
                )
            )
        return out[:k]


_matcher = None
_backend_name = "lexical"


def _get_matcher():
    global _matcher, _backend_name
    if _matcher is not None:
        return _matcher
    try:
        from ...config import settings

        if settings.prefer_dense_embeddings:
            _matcher = _DenseMatcher()
            _backend_name = "dense"
            return _matcher
    except Exception as exc:
        print(f"[aegis] dense script matching unavailable ({exc}); using lexical")
    _matcher = _LexicalMatcher()
    _backend_name = "lexical"
    return _matcher


def match_templates(text: str, k: int = 3) -> TemplateResult:
    """Match one utterance against the scam-script template library."""
    if not (text or "").strip():
        return TemplateResult(backend=_backend_name)
    matcher = _get_matcher()
    degraded = ["script:lexical"] if matcher.backend == "lexical" else []

    # Advisory text is suppressed before matching rather than after scoring.
    # Both backends need this: an embedding model places "never share your OTP"
    # very close to "tell me your OTP", because they are about the same thing.
    # Similarity is the wrong tool for detecting negation, so it is not asked to.
    if _is_advisory(text):
        return TemplateResult(matches=[], backend=matcher.backend, degraded=degraded)

    return TemplateResult(
        matches=matcher.match(text, k), backend=matcher.backend, degraded=degraded
    )


def status() -> dict:
    _get_matcher()
    return {"backend": _backend_name, "templates": len(TEMPLATES)}
