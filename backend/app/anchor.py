from .stellar_anchor import StellarAnchorService, stellar_anchor_service

anchor_integration = stellar_anchor_service
sep10_auth = stellar_anchor_service

__all__ = ["StellarAnchorService", "stellar_anchor_service", "anchor_integration", "sep10_auth"]
