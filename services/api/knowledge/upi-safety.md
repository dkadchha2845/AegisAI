<!-- tags: upi, payment, advisory -->
# UPI and payment mechanics

Retrieved by the artifact analyzer when a UPI ID, QR code, or transaction
screenshot is submitted. The rules here are mechanical properties of the UPI
system, which is what makes them usable as evidence rather than advice.

## Receiving money never requires a PIN

A UPI PIN authorises money leaving an account. It is never required to
receive. Any instruction to "enter your PIN to accept the refund", scan a QR
code "to receive the cashback", or approve a collect request "so the money can
come in" is an instruction to send money, described backwards.

This is the single most useful fact in the whole corpus, because it converts a
judgement call ("does this feel like a scam?") into a mechanical check ("is
this asking me to authorise an outgoing payment?").

## Scanning a QR code sends money, it does not receive it

UPI QR codes encode a payee. Scanning one and completing the flow always
results in money leaving the scanner's account. A QR code sent by someone who
owes you money is a request for you to pay them again.

## Collect requests are pull payments

A "collect request" asks the recipient to approve an outgoing transfer.
Fraudulent collect requests are often labelled with reassuring text in the
remarks field — "refund", "cashback", "verification" — because the remarks are
attacker-controlled free text and appear in the approval screen as if the
system had generated them.

## The verified payee name is the thing to read

Before approving, the app shows the name registered against the VPA at the
beneficiary bank. That name comes from the bank's KYC record and cannot be set
by the payee. If a caller claims to be from a bank, a court, or a government
department and the registered name on the VPA is an individual or an
unrelated business, the claim and the account do not match.

A mismatch between claimed identity and registered payee name is the strongest
single signal available in the UPI flow.

## No government body collects fines or fees by UPI to a personal VPA

Legitimate government payments run through official portals — Bharatkosh, the
e-challan system, state treasury gateways, the court's own e-payment facility.
They do not run through a personal `@okaxis` or `@paytm` handle supplied over
a phone call.

## Handle suffixes indicate the PSP, not legitimacy

The part after the `@` identifies the payment service provider (`@oksbi`,
`@okhdfcbank`, `@ybl`, `@paytm`, `@axl`). It says nothing about who owns the
account or whether they are trustworthy. A handle that looks like a bank's is
not a bank account — anyone can register a VPA with a bank-branded suffix.

Conversely, a VPA that *imitates* an institution in its local part —
`sbi.refund@`, `rbi.verify@`, `cybercell.gov@` — is impersonating, because
institutions do not collect from citizens this way at all.

## Transaction limits shape the script

Per-transaction and daily UPI limits are why a large fraudulent transfer is
usually split across several payments, or moved to IMPS/NEFT/RTGS partway
through. A caller who reacts to a failed transfer by immediately proposing a
different rail, or by splitting the amount, is working around a limit — which
means the amount, not the recipient, is what they care about.

## Reversal is not automatic

A completed UPI transfer to the wrong or fraudulent payee is not reversible by
the sender. Recovery runs through the bank's fraud process and the 1930 / 
cybercrime.gov.in reporting chain, and depends on the funds still sitting in
the beneficiary account. Speed is the only lever the victim has.
