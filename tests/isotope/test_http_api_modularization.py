from isotope.interfaces.http import HttpApiApp, HttpResponse
from isotope.interfaces.http_artifact_routes import HttpArtifactRouteMixin
from isotope.interfaces.http_dispatch import HttpDispatchMixin
from isotope.interfaces.http_llm_routes import HttpLlmRouteMixin
from isotope.interfaces.http_product_routes import HttpProductRouteMixin
from isotope.interfaces.http_responses import HttpResponseMixin
from isotope.interfaces.http_routes import HttpRouteMixin
from isotope.interfaces.http_run_routes import HttpRunRouteMixin
from isotope.interfaces.http_serialization import HttpSerializationMixin
from isotope.interfaces.http_types import HttpResponse as SplitHttpResponse
from isotope.interfaces.http_validation import HttpValidationMixin


def test_http_api_app_facade_preserves_modular_boundaries():
    assert HttpResponse is SplitHttpResponse
    assert issubclass(HttpApiApp, HttpDispatchMixin)
    assert issubclass(HttpApiApp, HttpResponseMixin)
    assert issubclass(HttpApiApp, HttpRouteMixin)
    assert issubclass(HttpApiApp, HttpSerializationMixin)
    assert issubclass(HttpApiApp, HttpValidationMixin)


def test_http_dispatch_uses_domain_route_handler_mixins():
    assert issubclass(HttpDispatchMixin, HttpArtifactRouteMixin)
    assert issubclass(HttpDispatchMixin, HttpLlmRouteMixin)
    assert issubclass(HttpDispatchMixin, HttpProductRouteMixin)
    assert issubclass(HttpDispatchMixin, HttpRunRouteMixin)
    assert "_dispatch_request" in HttpDispatchMixin.__dict__
