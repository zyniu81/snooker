from django.contrib.auth.tokens import PasswordResetTokenGenerator

class AccountActivationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # We generate a hash based on the user ID, time and verification status
        return (
            str(user.pk) + str(timestamp) + str(user.profile.email_confirmed)
        )

account_activation_token = AccountActivationTokenGenerator()