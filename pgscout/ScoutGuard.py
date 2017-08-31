from pgscout.Scout import Scout
from pgscout.config import use_pgpool
from pgscout.utils import load_pgpool_account


class ScoutGuard(object):

    def __init__(self, auth, username, password, job_queue):
        self.job_queue = job_queue
        self.active = True

        # Set up initial account
        initial_account = {
            'auth_service': auth,
            'username': username,
            'password': password
        }
        if not username and use_pgpool():
            initial_account = load_pgpool_account(1)
        self.acc = self.init_scout(initial_account)

    def init_scout(self, acc_data):
        return Scout(acc_data['auth_service'], acc_data['username'], acc_data['password'], self.job_queue)

    def run(self):
        while True:
            self.active = True
            self.acc.run()
            self.active = False

            # Scout terminated, probably (shadow)banned.
            if use_pgpool():
                self.swap_account()
            else:
                # Just stop.
                self.active = False
                break

    def swap_account(self):
        # First get new account, then release to avoid getting same account back.
        new_acc = self.init_scout(load_pgpool_account(1))
        self.acc.update_pgpool(release=True, reason=self.acc.last_msg)
        self.acc = new_acc
