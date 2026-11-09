"""Google Gemini's structured extraction contract."""
from typing import Literal
from pydantic import BaseModel, Field

FieldName = Literal[
    'company_name', 'berlin_presence', 'address', 'city',
    'residential_management', 'weg_management', 'commercial_management',
    'portfolio_units', 'heating_billing_relevance',
    'portfolio_complexity', 'digital_operations_fit',
    'general_email', 'telephone',
]

class ProposedFact(BaseModel):
    field: FieldName
    value: str = Field(description="Short grounded value, or Yes/No for boolean fields")
    page_id: int
    quote: str = Field(description="Exact unmodified substring copied from that page")

class ProposedContact(BaseModel):
    name: str
    role: str = ''
    email: str = ''
    phone: str = ''
    linkedin_url: str = ''
    page_id: int
    quote: str = Field(description="Exact substring containing person's name and ideally email")

class Extraction(BaseModel):
    facts: list[ProposedFact] = Field(default_factory=list)
    contacts: list[ProposedContact] = Field(default_factory=list)
