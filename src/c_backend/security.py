import hashlib
import hmac


def verify_meta_signature(
    body: bytes,
    signature: str | None,
    app_secret: str,
) -> bool:
    if signature is None:
        return False

    if not signature.startswith("sha256="):
        return False

    expected_signature = (
        "sha256="
        + hmac.new(
            app_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(
        signature,
        expected_signature,
    )
