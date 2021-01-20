import psutil
import signal
import os
from mailfetcher.models import Mail
from django.conf import settings
from mailfetcher.crons.mailCrawler.analysis.leakage import (
    analyze_mail_connections_for_leakage,
)
from mailfetcher.crons.mailCrawler.analysis.viewMail import (
    call_openwpm_view_mail,
)
from mailfetcher.crons.mailCrawler.analysis.clickLinks import (
    call_openwpm_click_links,
)


def kill_openwpm(ignore=[]):
    for proc in psutil.process_iter():
        # check whether the process name matches
        if proc.pid in ignore:
            continue
        if proc.name() in ["geckodriver", "firefox", "firefox-bin", "Xvfb"]:
            # Kill process tree
            gone, alive = kill_proc_tree(proc.pid)
            for p in alive:
                ignore.append(p.pid)
            # Recursively call yourself to avoid dealing with a stale PID list
            return kill_openwpm(ignore=ignore)


def kill_proc_tree(
    pid, sig=signal.SIGTERM, include_parent=True, timeout=1, on_terminate=None
):
    """Kill a process tree (including grandchildren) with signal
    "sig" and return a (gone, still_alive) tuple.
    "on_terminate", if specified, is a callabck function which is
    called as soon as a child terminates.
    """
    assert pid != os.getpid(), "won't kill myself"
    parent = psutil.Process(pid)
    children = parent.children(recursive=True)
    if include_parent:
        children.append(parent)
    for p in children:
        p.send_signal(sig)
    gone, alive = psutil.wait_procs(children, timeout=timeout, callback=on_terminate)
    return (gone, alive)


def analyzeOnView():
    # Load Mail Queue
    mail_queue = Mail.objects.filter(
        processing_state=Mail.PROCESSING_STATES.UNPROCESSED
    ).exclude(processing_fails__gte=settings.OPENWPM_RETRIES)[
        : settings.CRON_MAILQUEUE_SIZE
    ]
    mail_queue_count = mail_queue.count()

    if settings.RUN_OPENWPM and mail_queue_count > 0:
        print("Viewing %s mails." % mail_queue_count)
        # Analyze the email queue
        failed_mails = call_openwpm_view_mail(mail_queue)
        print(
            "{} mail views of {} failed in openWPM.".format(
                len(failed_mails), mail_queue_count
            )
        )

    # Clean up zombie processes
    kill_openwpm()


def analyzeOnClick():
    # Load Mail Queue
    mail_queue = Mail.objects.filter(
        processing_state=Mail.PROCESSING_STATES.VIEWED
    ).exclude(processing_fails__gte=settings.OPENWPM_RETRIES)[
        : settings.CRON_MAILQUEUE_SIZE
    ]

    mail_queue_count = mail_queue.count()
    # Now we want to click some links
    if settings.VISIT_LINKS and settings.RUN_OPENWPM and mail_queue_count > 0:
        link_mail_map = {}
        print("Visiting %s links." % mail_queue_count)
        for mail in mail_queue:
            # Get a link that is not an unsubscribe link
            link = mail.get_non_unsubscribe_link()
            if "http" in link:
                link_mail_map[link] = mail
            else:
                print(
                    "Couldn't find a link to click for mail: {}. Skipping.".format(mail)
                )
                mail.processing_state = Mail.PROCESSING_STATES.NO_UNSUBSCRIBE_LINK
                mail.save()
        # Visit the links
        failed_urls = call_openwpm_click_links(link_mail_map)
        print(
            "{} urls of {} failed in openWPM.".format(
                len(failed_urls), mail_queue_count
            )
        )


def analyzeLeaks():
    # Load Mail Queue
    if settings.VISIT_LINKS:
        mail_queue = Mail.objects.filter(
            processing_state=Mail.PROCESSING_STATES.LINK_CLICKED
        )
    else:
        mail_queue = Mail.objects.filter(processing_state=Mail.PROCESSING_STATES.VIEWED)

    print("Analyzing {} mails for leakages.".format(mail_queue.count()))
    # Check if the email address is leaked somewhere (hashes, ...)
    for mail in mail_queue:
        analyze_mail_connections_for_leakage(mail)
        mail.create_service_third_party_connections()
        mail.processing_state = Mail.PROCESSING_STATES.DONE
        service = mail.get_service()
        if service is not None:
            service.resultsdirty = True
            service.save()
        mail.save()
