"""§16 Testing — VIZ-02's object-storage half. upload_glb() never
raises: unconfigured storage and a failed upload both degrade to None,
mirroring VIS-04's "never block the pipeline" discipline.
"""

from unittest.mock import MagicMock, patch

from solarfit.providers.storage import upload_glb


def test_upload_glb_returns_none_when_unconfigured():
    settings = MagicMock(object_storage_bucket="", object_storage_endpoint_url="")
    with (
        patch("solarfit.providers.storage.get_settings", return_value=settings),
        patch("solarfit.providers.storage.boto3.client") as client_cls,
    ):
        result = upload_glb(b"fake-glb-bytes", key="panorama/abc.glb")

    assert result is None
    client_cls.assert_not_called()


def test_upload_glb_returns_url_on_success():
    settings = MagicMock(
        object_storage_bucket="solarfit-panoramas",
        object_storage_endpoint_url="https://storage.example.com",
        object_storage_access_key="key",
        object_storage_secret_key="secret",
    )
    mock_client = MagicMock()
    with (
        patch("solarfit.providers.storage.get_settings", return_value=settings),
        patch("solarfit.providers.storage.boto3.client", return_value=mock_client),
    ):
        result = upload_glb(b"fake-glb-bytes", key="panorama/abc.glb")

    assert result == "https://storage.example.com/solarfit-panoramas/panorama/abc.glb"
    mock_client.put_object.assert_called_once()
    _, kwargs = mock_client.put_object.call_args
    assert kwargs["Bucket"] == "solarfit-panoramas"
    assert kwargs["Key"] == "panorama/abc.glb"
    assert kwargs["Body"] == b"fake-glb-bytes"


def test_upload_glb_returns_none_on_client_error():
    from botocore.exceptions import ClientError

    settings = MagicMock(
        object_storage_bucket="solarfit-panoramas",
        object_storage_endpoint_url="https://storage.example.com",
        object_storage_access_key="key",
        object_storage_secret_key="secret",
    )
    mock_client = MagicMock()
    mock_client.put_object.side_effect = ClientError({"Error": {"Code": "500", "Message": "boom"}}, "PutObject")
    with (
        patch("solarfit.providers.storage.get_settings", return_value=settings),
        patch("solarfit.providers.storage.boto3.client", return_value=mock_client),
    ):
        result = upload_glb(b"fake-glb-bytes", key="panorama/abc.glb")

    assert result is None
