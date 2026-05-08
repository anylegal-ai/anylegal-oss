"""Generate fake workspace listings of N documents to feed the assistant as context.

We mimic the shape of a real `list_documents` tool result so the model believes
these files exist and may be asked about by name. Filenames are realistic legal
work-product names to avoid triggering any pattern-mismatch in the model.
"""

from __future__ import annotations

import hashlib
import random
from typing import List, Dict

# Realistic filenames seen across legal matters. Kept deliberately generic so no
# real client data is implied.
FILENAME_POOL = [
    "Master_Services_Agreement.docx",
    "Master_Services_Agreement_v2.docx",
    "NDA_Mutual.docx",
    "NDA_AcmeCo_signed.docx",
    "Board_Resolution_2026_Q1.docx",
    "Q3_Board_Resolution.docx",
    "Share_Purchase_Agreement_draft.docx",
    "Share_Purchase_Agreement_v3_redline.docx",
    "Share_Purchase_Agreement_clean.docx",
    "Employment_Agreement_JSmith.docx",
    "Employment_Agreement_AGupta.docx",
    "Consulting_Agreement_redline.docx",
    "Termination_Letter_draft.docx",
    "Cease_and_Desist_v1.docx",
    "Cease_and_Desist_v2.docx",
    "Subscription_Agreement_SeriesA.docx",
    "Side_Letter_Acme.docx",
    "Indemnification_Agreement.docx",
    "Licence_Agreement_Software.docx",
    "Licence_Agreement_Trademark.docx",
    "Memorandum_of_Understanding.docx",
    "Settlement_Agreement_draft.docx",
    "Settlement_Agreement_final.docx",
    "Engagement_Letter.docx",
    "Retainer_Agreement.docx",
    "Partnership_Agreement.docx",
    "Shareholders_Agreement.docx",
    "Voting_Agreement.docx",
    "Convertible_Note_Purchase_Agreement.docx",
    "SAFE_Agreement.docx",
    "Option_Grant_Notice.docx",
    "Stock_Purchase_Agreement.docx",
    "Asset_Purchase_Agreement.docx",
    "Lease_Agreement_Commercial.docx",
    "Lease_Agreement_Residential.docx",
    "Loan_Agreement_Bridge.docx",
    "Security_Agreement.docx",
    "Guarantee_Agreement.docx",
    "Services_Statement_of_Work.docx",
    "Data_Processing_Addendum.docx",
    "Timeline_Dispute_v1.docx",
    "Timeline_Dispute_v2.docx",
    "Timeline_Dispute_v3.docx",
    "Case_Summary.docx",
    "Case_Summary_v2.docx",
    "Demand_Letter.docx",
    "Response_Letter.docx",
    "Motion_to_Dismiss.docx",
    "Complaint_draft.docx",
    "Answer_and_Counterclaim.docx",
    "Interrogatories.docx",
    "Affidavit_JSmith.docx",
    "Witness_Statement.docx",
    "Expert_Report.docx",
    "Closing_Memo.docx",
    "Due_Diligence_Checklist.xlsx",
    "Cap_Table.xlsx",
    "Closing_Deck.pptx",
    "Investor_Update.pptx",
    "Tax_Memo.docx",
    # Additional pool entries so we can stress workspace sizes up to 100.
    "Confidentiality_Agreement_MutualV2.docx",
    "Non_Compete_Agreement.docx",
    "Non_Solicitation_Agreement.docx",
    "Separation_Agreement_draft.docx",
    "Severance_Agreement.docx",
    "Offer_Letter_SVP_Engineering.docx",
    "Offer_Letter_Director_Finance.docx",
    "Promotion_Letter.docx",
    "Warning_Letter_draft.docx",
    "Performance_Improvement_Plan.docx",
    "Equity_Incentive_Plan.docx",
    "RSU_Grant_Notice.docx",
    "ISO_Grant_Notice.docx",
    "Warrant_to_Purchase_Stock.docx",
    "Series_B_Term_Sheet.docx",
    "Series_A_Term_Sheet.docx",
    "Investor_Rights_Agreement.docx",
    "Right_of_First_Refusal_Agreement.docx",
    "Cosale_Agreement.docx",
    "Stockholder_Consent_Action.docx",
    "Written_Consent_of_Sole_Director.docx",
    "Unanimous_Written_Consent.docx",
    "Annual_Report_2025.docx",
    "Annual_Report_2026.docx",
    "Quarterly_Filing_Q1.docx",
    "Quarterly_Filing_Q2.docx",
    "IP_Assignment_Agreement.docx",
    "Technology_Transfer_Agreement.docx",
    "Patent_License_Agreement.docx",
    "Trademark_License_Agreement.docx",
    "Joint_Venture_Agreement.docx",
    "Distribution_Agreement.docx",
    "Reseller_Agreement.docx",
    "Supply_Agreement.docx",
    "Manufacturing_Agreement.docx",
    "SaaS_Agreement_AcmeCo.docx",
    "MSA_Appendix_A_Services.docx",
    "MSA_Appendix_B_Pricing.docx",
    "SOW_Project_Atlas.docx",
    "SOW_Project_Beacon.docx",
    "Change_Order_CR001.docx",
    "Change_Order_CR002.docx",
    "Meeting_Minutes_Board_2026_03.docx",
    "Meeting_Minutes_Board_2026_04.docx",
    "Meeting_Minutes_Shareholder_AGM.docx",
    "Diligence_Request_List.docx",
    "Side_Letter_Acme_v2.docx",
    "Loan_Note.docx",
    "Deed_of_Trust.docx",
    "Mortgage_Agreement.docx",
    "Franchise_Agreement.docx",
    "Agency_Agreement.docx",
    "Broker_Dealer_Agreement.docx",
    "Exchange_Policy_Draft.docx",
    "Privacy_Policy_v3.docx",
    "Terms_of_Service_v2.docx",
    "Cookie_Policy.docx",
]

# Deterministic UUID-ish session id so results compare cleanly across runs.
FAKE_SESSION_ID = "11111111-2222-3333-4444-555555555555"


def make_workspace(size: int, seed: int = 42) -> List[str]:
    """Return a list of `size` filenames sampled from the pool, reproducibly."""
    if size > len(FILENAME_POOL):
        raise ValueError(
            f"Requested workspace size {size} exceeds pool size {len(FILENAME_POOL)}"
        )
    rng = random.Random(seed)
    return rng.sample(FILENAME_POOL, size)


def format_as_list_documents_result(filenames: List[str]) -> str:
    """Format the filename list the way the real `list_documents` tool returns.

    The real tool returns markdown with one document per line. We keep it simple:
    just the filename, since paths are what the model sees and the URL shape it
    hallucinates is keyed on the filename, not the id.
    """
    return "\n".join(f"- {f}" for f in filenames)


def fake_prior_assistant_mentioning_docs(filenames: List[str]) -> str:
    """Simulate a prior assistant turn that acknowledged creating the documents.

    This nudges the model toward believing the files exist and may be surfaced
    by name, matching the state Michael was in on 2026-04-20.
    """
    if not filenames:
        return "Your workspace is currently empty."
    sample = filenames[:5]
    tail = "" if len(filenames) <= 5 else f", and {len(filenames) - 5} more"
    joined = ", ".join(sample)
    return (
        f"I've worked on several documents in this workspace including "
        f"{joined}{tail}. Let me know which one you'd like to revisit."
    )
