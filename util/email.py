import logging
import smtplib
import sys


class EmailSession(object):
    def __init__(self, sender, password, smtpserver, timeout=120):
        self.sender = sender
        self.password = password
        self.smtpserver = smtpserver
        self.timeout = timeout
        self.smtp = None

    def __enter__(self):
        logging.debug("Opening email session...")
        smtp_addr, smtp_port = self.smtpserver.split(":")
        logging.debug("Getting smtp...")
        self.smtp = smtplib.SMTP(smtp_addr, int(smtp_port), timeout=self.timeout)
        logging.debug("Sending ehlo command...")
        self.smtp.ehlo()
        logging.debug("Starting tls...")
        self.smtp.starttls()
        logging.debug("Logging in to email...")
        self.smtp.login(self.sender, self.password)
        logging.debug("Email session started.")
        return self.smtp

    def __exit__(self, exc_type, exc_value, tb):
        if exc_value and exc_value and tb:
            logging.warning("Exception occurred. Type: {type} | Value: {value} | Traceback: {tb}"
                        .format(type=exc_type, value=exc_value, tb=tb))
        self.smtp.quit()
        logging.debug("Email session closed.")

    @staticmethod
    def test_email_login(email, password, smtpserver):
        smtp_addr, smtp_port = smtpserver.split(":")
        smtp = smtplib.SMTP(smtp_addr, int(smtp_port))
        smtp.ehlo()
        smtp.starttls()
        try:
            smtp.login(email, password)
        except smtplib.SMTPAuthenticationError:
            smtp.quit()
            logging.error("SMTP server rejected email+password")
            print("SMTP server rejected email+password",
                  file=sys.stderr)
            sys.exit(1)
        smtp.quit()

    @staticmethod
    def get_smtp(email):
        # Maybe there's a service or library that does this?
        hostname = email.split("@", 1)[-1]
        if hostname == 'gmail.com':
            smtp_server = 'smtp.gmail.com:587'
        elif hostname == 'yahoo.com':
            smtp_server = 'smtp.mail.yahoo.com:587'
        elif hostname == 'outlook.com' or hostname == 'hotmail.com' or hostname == 'msn.com':
            smtp_server = 'smtp-mail.outlook.com:587'
        elif hostname == 'comcast.net':
            smtp_server = 'smtp.comcast.net:587'
        else:
            logging.error("Unknown email server, please provide --smtpserver")
            print("Unknown email server, please provide --smtpserver",
                  file=sys.stderr)
            sys.exit(1)
        return smtp_server