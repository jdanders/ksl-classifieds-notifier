#!/usr/bin/env python3
import os
import sys
import argparse
import logging
import time
import datetime
import getpass
import smtplib
import socket
from ksl import KSL, Listing


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


def format_listings(query_result, seen, head):
    new_seen = seen.copy()
    listings_formatted = []
    for listing in query_result:
        if listing.link not in seen:
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
            listing_formatted = listing_formatted.encode('ascii', 'ignore').decode()

            listings_formatted.append(listing_formatted)

            # Track seen results
            new_seen.append(listing.link)

    return listings_formatted, new_seen


def check_ksl(args, queries, seen, receiver, sender, passwd, smtpserver):
    # create the thin object
    ksl = KSL()

    head = args['head']
    char_limit = args["char_limit"]

    for query, html_data in ksl.search(queries, **args):
        if query not in seen:
            seen[query] = []

        query_result = ksl.find_elements(html_data)

        listings, new_seen_list = format_listings(query_result, seen[query], head)

        message_bodies = create_message_bodies(query, listings, char_limit)

        # Email new results
        messages = []
        current_time = get_current_time()
        for i, message_body in enumerate(message_bodies):
            message = MESSAGE_TEMPLATE.format(subject=SUBJECT_TEMPLATE.format(query=query,
                                                                              n=i + 1,
                                                                              total=len(message_bodies),
                                                                              time=current_time),
                                              receiver=receiver,
                                              sender=sender.format(mail=sender),
                                              body=message_body)
            messages.append(message)

        send_emails(receiver, sender, passwd, smtpserver, messages)

        if len(message_bodies) == 0:
            logging.info("No new search results found. No email sent.")

        # Save of results for next time
        seen[query] = new_seen_list
    return seen


def send_emails(receiver, sender, password, smtpserver, messages):
    smtp_addr, smtp_port = smtpserver.split(":")
    smtp = smtplib.SMTP(smtp_addr, int(smtp_port))
    smtp.ehlo()
    smtp.starttls()
    smtp.login(sender, password)

    for i, message in enumerate(messages):
        logging.info("Sending email {n} of {total}".format(n=i + 1, total=len(messages)))
        smtp.sendmail(sender.format(mail=sender), receiver, message)
        logging.debug("Sent this message:\n{message}".format(message=message))

    smtp.quit()


def get_current_time():
    return datetime.datetime.now().strftime("%H:%M")


def create_message_bodies(search_term, listings, char_limit):
    header = HEADER_TEMPLATE.format(plural="es" if len(listings) > 0 else "", query=search_term)
    subject_count = len(SUBJECT_TEMPLATE.format(query=search_term,
                                                n=len(listings),
                                                total=len(listings),
                                                time=get_current_time()))

    message_bodies = []
    listings_report = ""

    # If there's a character limit, break the report into parts so that no part exceeds char_limit.
    for listing in listings:
        if char_limit:
            # If listing pushes message body past character count, store message body without adding the listing.
            # Note: Subject is included in char count since it's included in the message body when sent through SMS.
            if len(listings_report) + len(listing) + len(header) + subject_count > char_limit:
                message_bodies.append(BODY_TEMPLATE.format(header=header, listings_report=listings_report))
                listings_report = ""

        listings_report += listing

    if len(listings) > 0:
        message_bodies.append(BODY_TEMPLATE.format(header=header, listings_report=listings_report))

    return message_bodies


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
    loop_delay = args.pop('time') * 60
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

    # Fork to background
    foreground = args.pop('foreground')
    if not foreground:
        pid = os.fork()
        if pid:
            print ("Sending notifier to background with pid %d" % pid)
            print ("  use 'kill %d' to kill the process" % pid)
            sys.exit()

    # Dictionary to store results of queries
    seen = {}

    # find our results
    queries = args.pop('query')
    exception_thresh = int(args.pop('emailexceptions')) * 10
    exception_count = 0
    today = None
    while True:
        try:
            seen = check_ksl(args, queries, seen, receiver, sender, passwd, smtpserver)
            # log seen list daily for debug
            if (today != datetime.date.today()):
                logging.debug("seen list: %s"%(seen))
                today = datetime.date.today()
            if exception_count > 0:
                exception_count -= 1
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
                    logging.info("Sending exception message to {sender}".format(sender=sender))
                    send_emails(sender,
                                sender,
                                passwd,
                                smtpserver,
                                [MESSAGE_TEMPLATE.format(subject="KSL Notifier Failure",
                                                       receiver=sender,
                                                       sender=sender,
                                                       body="Exception in script detected.\n"
                                                            "Exception count %d\n"
                                                            "The script will die after the count reaches 10\n"
                                                            "%s"
                                                            % (exception_count / 10, exc_txt))])
            except:
                pass
            # If there is something more basic failing, the count trigger
            # a final failure of the loop.
            if exception_count > 100:
                logging.error("Too many exceptions, terminating")
                raise
        time.sleep(loop_delay)


if __name__ == '__main__':
    p = argparse.ArgumentParser(
        description=('ksl_notify - command line utility to notify of '
                     'new KSL classifieds ads')
    )

    p.add_argument('--email', default=None,
                   help='email address from which to send. '
                        'If --receiver is not specified, this email will also be used as the receiver.')
    p.add_argument('--smtpserver', default='',
                   help='email SMTP server:port, should be unneeded for '
                   'gmail, outlook, hotmail, msn, yahoo, or comcast')
    p.add_argument('--receiver', default=None,
                   help='email address to send the email to. Defaults to --email value.')
    p.add_argument('-t', '--time', nargs='?', default=10, const=int, type=int,
                   help='Number of minutes to wait between searches')
    p.add_argument('-l', '--logfile', default=None,
                   help='File to log output from daemon process, defaults '
                   'to stdout')
    p.add_argument('--loglevel', default="INFO",
                   help='Choose level: debug, info, warning')
    p.add_argument('query', nargs='+', action='store', default=None,
                   help='List of terms to search on KSL classifieds. '
                   'Use quotes for multiword searches')
    p.add_argument('-x', '--expand-search', action='store_const', default=0, const=1,
                   help='Include listings more broadly related to your search terms.')
    p.add_argument('-c', '--category', default=None,
                   help='Category to apply to search results')
    p.add_argument('-u', '--subcategory', default=None, dest='subCategory',
                   help='Category to apply to search results')
    p.add_argument('-m', '--min-price', default='0',
                   help='Minimum dollar amount to include in search results')
    p.add_argument('-M', '--max-price', default='0',
                   help='Maximum dollar amount to include in search results')
    p.add_argument('-z', '--zip', default=None,
                   help='ZIP code around which to center search results')
    p.add_argument('--city', default=None,
                   help='City around which to center search results')
    p.add_argument('--state', default=None,
                   help='State (abbr, like UT) around which to center search '
                   'results')
    p.add_argument('-d', '--miles', default=None,
                   help='Maximum distance in miles from ZIP code center')
    p.add_argument('-n', '--perPage', default=None,
                   help='Number of results to include in search results.'
                   '(Does not seem to work!)')
    p.add_argument('--head', default=None, type=int,
                   help="Number of lines to include from the listing's description.")
    p.add_argument('--char-limit', default=None, type=int,
                   help="Number of characters allowed in the message body. " 
                        "Listings that exceed the character count will be sent in additional messages.")
    p.add_argument('-r', '--reverse', action='store_const',
                   default=0, const=1, dest='sort',
                   help='If included, query will sort oldest to newest. '
                   'Default is newest to oldest')
    p.add_argument('-s', '--sold', action='store_const', default=0, const=1,
                   help='If included, query will return results for sold '
                   'items as well as active items')
    p.add_argument('-f', '--foreground', action='store_const', default=0,
                   const=1,
                   help='Do not fork to background')
    p.add_argument('-e', '--emailexceptions', default='5',
                   help='Number of repeated exceptions before sending emails')

    args = p.parse_args()

    main(vars(args))
