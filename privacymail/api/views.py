from django.views.generic import View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from identity.util import validate_domain
from django.conf import settings
from identity.models import Identity, Service
from mailfetcher.analyser_cron import create_service_cache
import logging
from random import shuffle
import os

logger = logging.getLogger(__name__)


class BookmarkletApiView(View):
    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        return super(BookmarkletApiView, self).dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            url = request.POST["url"]
            url = validate_domain(url)

            # Get or create the service matching this domain
            service, created = Service.get_or_create(url=url, name=url)
            service.save()

            # Select a domain to use for the identity
            # Create a list of possible domains
            domains = [cred["DOMAIN"] for cred in settings.MAILCREDENTIALS]
            # Shuffle it
            shuffle(domains)
            # Iterate through it
            for identityDomain in domains:
                # If the domain has not yet been used, stop the loop, otherwise try the next
                if Identity.objects.filter(service_id=service.pk).filter(mail__contains=identityDomain).count() == 0:
                    break
            # At this point, we have either selected a domain that has not yet been used for the
            # provided service, or the service already has at least one identity for each domain,
            # in which case we have picked one domain at random (by shuffling the list first).

            # Create an identity and save it
            ident = Identity.create(service, identityDomain)
            ident.save()

            if created:
                create_service_cache(service, force=True)

            # Return the created identity
            r = JsonResponse({
                "site": url,
                "email": ident.mail,
                "first": ident.first_name,
                "last": ident.surname,
                "gender": "Male" if ident.gender else "Female"
            })
        except KeyError:
            logger.warning("BookmarkletApiView.post: Malformed request received, missing url.", extra={'request': request})
            r = JsonResponse({"error": "No URL passed"})
        except AssertionError:
            # Invalid URL passed
            logger.warning("BookmarkletApiView.post: Malformed request received, malformed URL.", extra={'request': request})
            r = JsonResponse({"error": "Invalid URL passed."})
        r["Access-Control-Allow-Origin"] = "*"
        return r




class FrontendAppView(View):
    def get(self, request):
        print (os.path.join(settings.REACT_APP_DIR, 'build', 'index.html'))
        try:
            with open(os.path.join(settings.REACT_APP_DIR, 'build', 'index.html')) as f:
                #return HttpResponse(f.read())
        except FileNotFoundError:
            logging.exception('Production build of app not found')
            return HttpResponse(
                """
                This URL is only used when you have built the production
                version of the app. Visit http://localhost:3000/ instead, or
                run `npm run build` to test the production version.
                """,
                status=501,
            )

class StatisticTestView(View):
    def get_global_stats(self):
        return {
            "I am": "Fontend Statistic Test View",
            # TODO Ensure that service has at least 1 confirmed ident
            "service_count": "Service.objects.count()",
            # TODO Model will be renamed on merge
            "tracker_count": "a",
        }

    def get(self, request, *args, **kwargs):
        # Get the last approved services
        return JsonResponse({"global_stats": self.get_global_stats()})

