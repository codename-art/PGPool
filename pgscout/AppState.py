import logging

log = logging.getLogger(__name__)

class AppState(object):

    def __init__(self):
        self.accept_new_requests = True

    def toggle_new_requests(self):
        self.accept_new_requests = not self.accept_new_requests
        verb = "accepting" if self.accept_new_requests else "rejecting"
        log.info("Now {} new requests.".format(verb))
