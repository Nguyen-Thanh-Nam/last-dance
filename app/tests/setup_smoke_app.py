"""Local fixture server used only by scripts/smoke_setup.py; never calls the Internet."""
from app.main import app
from app.collectors.base import CollectorResult
from app.collectors import passive, social
from app.pipeline import DnsCollector, CertificateTransparencyCollector, RdapCollector


CONTENT = '<title>Acme Robotics</title>Product: Acme Portal helps teams. <a href="https://app.acme.example/">Acme Portal</a><a href="https://www.facebook.com/AcmeRobotics">Facebook</a>'


def saved_page(url, *args, **kwargs):
    if url != "https://acme.example/":
        raise ValueError("fixture server does not fetch external URLs")
    return url, "text/html", CONTENT


def skipped(self, context):
    return CollectorResult(self.name, "skipped", "isolated curl fixture")


passive.fetch_scoped = saved_page
social.fetch_scoped = saved_page
for collector in (DnsCollector, CertificateTransparencyCollector, RdapCollector):
    collector.collect = skipped
