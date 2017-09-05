
class WebServer(object):
    def __init__(self):
        self.accept_new_requests = True

    def toggle_new_requests(self):
        self.accept_new_requests = not self.accept_new_requests

