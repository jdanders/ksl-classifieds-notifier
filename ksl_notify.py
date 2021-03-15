#!/usr/bin/env python3
import os
import sys
import logging
import time
import datetime
import getpass
import smtplib
import socket
import json
from ksl import KSL, Listing
from ksl_notify_cli_parser import KslNotifyCliParser


# Message strings
SUBJECT_TEMPLATE = "{query} search match on KSL Classifieds at {time} ({n} of {total})"
SENDER_TEMPLATE = "KSL Notify <{mail}>"
HEADER_TEMPLATE = "New match{plural} found for query {query}"
BODY_TEMPLATE = "\r\n".join([
    "{header}",
    "",
    "{listings_report}"])
MESSAGE_TEMPLATE = "\r\n".join([
    "Subject: {subject}",
    "To: {receiver}",
    "From: {sender}",
    "",
    "{body}"])


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


def format_listing(listing, head):
    description = listing.description

    # Take the first n lines of the description if head is specified
    if head:
        description = '\n'.join(listing.description.strip().split('\n')[:head])

    listing_formatted = ('*' * 25 +
                       '\n{listing.link}\n'
                       '{listing.title}\n'
                       '${listing.price} - {listing.age} - '
                       '{listing.city}, {listing.state}\n'
                       '*  {description}\n\n'.format(**locals()))

    # Kill non-ascii characters
    return listing_formatted.encode('ascii', 'ignore').decode()


def check_ksl(args, queries, seen, receiver, sender, passwd, smtpserver):
    # create the thin object
    ksl = KSL()

    head = args['head']
    char_limit = args["char_limit"]

    logging.debug("Beginning search...")
    for query, html_data in ksl.search(queries, **args):
        if query not in seen:
            seen[query] = []
            logging.debug("Initialized query {query} into seen dictionary.".format(query=query))

        logging.debug("Filtering out seen listings...")
        query_result = [listing for listing in ksl.find_elements(html_data) if listing.link not in seen[query]]
        logging.debug("Acquired {count} unseen listings: {listings}".format(count=len(query_result),
                                                                            listings=query_result))

        logging.debug("Creating message bodies for listings...")
        links_by_message_bodies = create_message_bodies(query, query_result, char_limit, head)
        logging.debug("Message bodies created.")

        # Email new results
        with EmailSession(sender, passwd, smtpserver) as emailSession:
            current_time = get_current_time()
            for i, (message_body, links) in enumerate(links_by_message_bodies.items()):
                message = MESSAGE_TEMPLATE.format(subject=SUBJECT_TEMPLATE.format(query=query,
                                                                                  n=i + 1,
                                                                                  total=len(links_by_message_bodies),
                                                                                  time=current_time),
                                                  receiver=receiver,
                                                  sender=sender.format(mail=sender),
                                                  body=message_body)

                logging.info("Sending email {n} of {total}".format(n=i + 1, total=len(links_by_message_bodies)))
                emailSession.sendmail(sender.format(mail=sender), receiver, message)
                # Save of results for next time
                seen[query].extend(links)
                logging.debug("Sent this message:\n{message}".format(message=message))

            if len(links_by_message_bodies) == 0:
                logging.info("No new search results found. No email sent.")

        logging.debug("{count} emails sent to {receiver}."
                      .format(count=len(links_by_message_bodies.keys()), receiver=receiver))
    return seen


def get_current_time():
    return datetime.datetime.now().strftime("%H:%M")


def create_message_bodies(search_term, listings, char_limit, head):
    formatted_listing_by_listing = {}
    for listing in listings:
        formatted_listing_by_listing[listing] = format_listing(listing, head)

    header = HEADER_TEMPLATE.format(plural="es" if len(listings) > 1 else "", query=search_term)
    subject_count = len(SUBJECT_TEMPLATE.format(query=search_term,
                                                n=len(listings),
                                                total=len(listings),
                                                time=get_current_time()))

    links_by_message_bodies = {}
    links = []
    listings_report = ""

    # If there's a character limit, break the report into parts so that no part exceeds char_limit.
    for listing, formatted_listing in formatted_listing_by_listing.items():
        if char_limit:
            # If listing pushes message body past character count, store message body without adding the listing.
            # Note: Subject is included in char count since it's included in the message body when sent through SMS.
            if len(listings_report) + len(formatted_listing) + len(header) + subject_count > char_limit:
                links_by_message_bodies[BODY_TEMPLATE.format(header=header, listings_report=listings_report)] = links
                listings_report = ""
                links = []
        links.append(listing.link)
        listings_report += formatted_listing

    if len(formatted_listing_by_listing) > 0:
        links_by_message_bodies[BODY_TEMPLATE.format(header=header, listings_report=listings_report)] = links

    return links_by_message_bodies


def save_seen(file, seen):
    logging.info("Saving file {file}".format(file=file))
    with open(file, 'w') as f:
        json.dump(seen, f, indent=2)


def load_seen(file):
    logging.info("Loading file {file}".format(file=file))
    with open(file, 'r') as f:
        return json.load(f)


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


def main(args):
    # Set up logging
    logfile = args.pop('logfile')
    if logfile:
        logging.basicConfig(filename=logfile, filemode='w',
                            format=('%(asctime)s %(module)s %(levelname)s'
                                    ': %(message)s'),
                            datefmt='%m/%d/%Y %I:%M:%S %p',)
    numeric_level = logging.INFO
    loglevel = args.pop('loglevel')
    if loglevel:
        numeric_level = getattr(logging, loglevel.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % loglevel)
        logging.getLogger().setLevel(numeric_level)

    # Get needed controls
    minutes = args.pop('time')
    loop_delay = minutes * 60
    sender = args.pop('email', None)
    smtpserver = args.pop('smtpserver', None)
    if not sender:
        sender = input("Enter email address to use: ")
    if not smtpserver:
        smtpserver = get_smtp(sender)
    passwd = getpass.getpass("Enter password for sending email from {email}: "
                             .format(email=sender))
    test_email_login(sender, passwd, smtpserver)

    receiver = args.pop('receiver', None)
    if not receiver:
        receiver = sender

    exception_receiver = args.pop('exception_receiver')
    if not exception_receiver:
        exception_receiver = sender

    # Fork to background
    foreground = args.pop('foreground')
    if not foreground:
        pid = os.fork()
        if pid:
            print("Sending notifier to background with pid %d" % pid)
            print("  use 'kill %d' to kill the process" % pid)
            sys.exit()

    # Dictionary to store results of queries
    load_file = args.pop("load")
    seen = load_seen(load_file) if load_file else {}

    save_file = args.pop("save")

    # find our results
    queries = args.pop('query')
    exception_thresh = int(args.pop('emailexceptions')) * 10
    exception_count = 0
    today = None
    while True:
        try:
            logging.debug("Checking KSL")
            seen = check_ksl(args, queries, seen, receiver, sender, passwd, smtpserver)
            # log seen list daily for debug
            if today != datetime.date.today():
                logging.debug("seen list: %s"%(seen))
                today = datetime.date.today()
            if exception_count > 0:
                exception_count -= 10
        # While looping in daemon mode, try to keep executing
        # This will catch bad server connections, etc.
        except KeyboardInterrupt:
            raise
        except socket.timeout:
            # This is frequent-ish, so don't report, but still keep track
            logging.debug("Socket timeout")
            exception_count += 10
        except Exception as e:
            logging.exception("Exception found in main loop")
            exception_count += 10
            try:
                exc_txt = str(e)
                if exception_count > exception_thresh:
                    with EmailSession(sender, passwd, smtpserver) as email_session:
                        logging.info("Sending exception message to {receiver}".format(receiver=exception_receiver))
                        email_session.sendmail(sender,
                                               exception_receiver,
                                               MESSAGE_TEMPLATE.format(subject="KSL Notifier Failure",
                                                                       receiver=exception_receiver,
                                                                       sender=sender,
                                                                       body="Exception in script detected.\n"
                                                                            "Exception count %d\n"
                                                                            "The script will die after the count reaches 10\n"
                                                                            "%s"
                                                                            % (exception_count / 10, exc_txt)))
            except e:
                logging.debug("There was an issue sending the exception message to {sender}. {e}".format(sender=sender, e=e))
            # If there is something more basic failing, the count trigger
            # a final failure of the loop.
            if exception_count > 100:
                logging.error("Too many exceptions, terminating")
                raise
        finally:
            if save_file:
                save_seen(save_file, seen)
            logging.debug("Exception count is {count}".format(count=exception_count/10))

        logging.debug("Sleeping for {minutes} minutes".format(minutes=minutes))
        time.sleep(loop_delay)


if __name__ == '__main__':
    args = KslNotifyCliParser().parser.parse_args()

    main(vars(args))
