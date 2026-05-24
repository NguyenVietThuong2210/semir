from .pos import Customer, SalesTransaction, SaleDetail
from .coupon import Coupon, CouponCampaign
from .user import Role, UserProfile
from .inventory import InventorySnapshot

__all__ = [
    "Customer",
    "SalesTransaction",
    "SaleDetail",
    "Coupon",
    "CouponCampaign",
    "Role",
    "UserProfile",
    "InventorySnapshot",
]
