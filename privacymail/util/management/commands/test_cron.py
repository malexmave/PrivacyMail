from django.core.management.base import BaseCommand
from django.core.cache import cache
from identity.models import Service, Identity
from mailfetcher.analyser_cron import (
    create_service_cache,
    analyse_dirty_services,
    create_third_party_cache,
    analyze_differences_between_similar_mails,
)

from mailfetcher.models import Thirdparty, Mail, Eresource
from identity.views import ServiceView
import traceback
import time


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        try:
            # t = time.time()
            # print("Needed seconds {}".format(time.time() - t))
            analyse_dirty_services()
            # create_service_cache(service[0])
            print("All done. Exiting.")
        except Exception:
            traceback.print_exc()
        print("Done")