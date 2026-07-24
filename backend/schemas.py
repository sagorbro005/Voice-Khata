from typing import Optional, List, Literal, Any, Union, Dict
from pydantic import BaseModel, Field


class LedgerEntrySchema(BaseModel):
    transaction_type: Literal["new_sale", "update_existing"] = Field(
        ..., description="Transaction type: new_sale | update_existing"
    )
    customer_name: str = Field(..., description="Customer name in Bangla script")
    item: Optional[str] = Field(None, description="Item description in Bangla script or null")
    quantity: Optional[str] = Field(None, description="Quantity in Bangla script or null")
    total_amount_taka: Optional[float] = Field(None, description="Total bill for new_sale or extra charge for update_existing")
    paid_now_taka: Optional[float] = Field(None, description="Amount paid in this specific utterance or null")
    paid_amount_taka: Optional[float] = Field(None, description="Absolute cumulative paid amount confirmed by user or null")
    due_amount_taka: Optional[float] = Field(None, description="Absolute due amount confirmed by user or null")
    stated_due_taka: Optional[float] = Field(None, description="Stated due amount overriding computed due or null")
    full_settlement: bool = Field(False, description="True when utterance implies due is fully cleared")
    matched_entry_id: Optional[int] = Field(None, description="ID of existing matched entry or null")


class UpdateEntryRequest(BaseModel):
    customer_name: str
    item: Optional[str] = None
    quantity: Optional[str] = None
    total_amount_taka: Optional[float] = None
    paid_amount_taka: Optional[float] = None
    due_amount_taka: Optional[float] = None


class TranscribeResponse(BaseModel):
    transcript: str


class ExtractRequest(BaseModel):
    transcript: str


class ExtractResponse(BaseModel):
    structured_entry: LedgerEntrySchema
    preview_update: Optional[Union[dict, List[dict]]] = None


class ConfirmRequest(BaseModel):
    entry: LedgerEntrySchema


class SummaryResponse(BaseModel):
    summary_text: str
    audio_url: Optional[str] = None


class ErrorResponse(BaseModel):
    error: str


# Daily Sales Log Multi-Item Schemas

class SaleItemSchema(BaseModel):
    item: str = Field(..., description="Item name in Bangla script")
    quantity: Optional[str] = Field(None, description="Quantity in Bangla script or null")
    unit_price_taka: Optional[float] = Field(None, description="Unit price per item in Taka or null")


class MultiItemSaleSchema(BaseModel):
    customer_name: Optional[str] = Field(None, description="Customer name in Bangla script or null")
    items: List[SaleItemSchema] = Field(..., description="List of items purchased")
    total_amount_taka: float = Field(..., description="Overall transaction total amount in Taka")


class DailySaleExtractRequest(BaseModel):
    transcript: str


class DailySaleExtractResponse(BaseModel):
    structured_entry: MultiItemSaleSchema


class DailySaleConfirmRequest(BaseModel):
    entry: MultiItemSaleSchema


class InsightsAskRequest(BaseModel):
    transcript: str


class InsightsAskResponse(BaseModel):
    answer_text: str
    audio_url: Optional[str] = None

