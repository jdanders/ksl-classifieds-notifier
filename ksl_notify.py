#!/usr/bin/env python3
import os
import sys
import logging
import time
import datetime
import getpass
import socket

from util.email import EmailSession
from util import io
from ksl import KSL
from cli.ksl_notify_cli import KslNotifyCli

# Message strings
SUBJECT_TEMPLATE = "{query} search match on KSL Classifieds at {time} ({n} of {total})"
SENDER_TEMPLATE = "KSL Notify <{sender}>"
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


def check_ksl(args, queries, seen, receiver, sender, passwd, smtpserver):
    # create the thin object
    ksl = KSL()
    logging.debug("Beginning search...")
    for query, html_data in ksl.search(queries, **args):
        if query not in seen:
            seen[query] = []
            logging.debug("Initialized query {query} into seen dictionary.".format(query=query))

        # ********************* LOGGING HTML DATA *********************
        # print("*****************************************", type(html_data))

        # file1 = open("query-data.html", "w")
        # file1.write(query)
        # file1.close()


        # file1 = open("html-data.html", "wb")
        # file1.write(html_data)
        # file1.close()


        logging.debug("Filtering out seen listings...")
        query_result = [listing for listing in ksl.find_elements(html_data) if listing.link not in seen[query]]
        logging.debug("Acquired {count} unseen listings: {listings}".format(count=len(query_result),
                                                                            listings=query_result))

        logging.debug("Creating message bodies for listings...")
        links_by_message_body = create_message_bodies(query,
                                                      query_result,
                                                      args['char_limit'],
                                                      args['head'],
                                                      args['exclude_links'])

        # Email new results
        with EmailSession(sender, passwd, smtpserver) as email_session:
            for i, (message_body, links) in enumerate(links_by_message_body.items()):
                # Format templates
                subject = SUBJECT_TEMPLATE.format(query=query,
                                                  total=len(links_by_message_body),
                                                  n=i + 1,
                                                  time=get_time())

                message = MESSAGE_TEMPLATE.format(subject=subject,
                                                  sender=SENDER_TEMPLATE.format(sender=sender),
                                                  receiver=receiver,
                                                  body=message_body)

                logging.info("Sending email {n} of {total}".format(n=i + 1, total=len(links_by_message_body)))
                email_session.sendmail(sender.format(mail=sender), receiver, message)
                # Store results for next time
                seen[query].extend(links)
                logging.debug("Sent this message:\n{message}".format(message=message))

            if len(links_by_message_body) == 0:
                logging.info("No new search results found. No email sent.")

        logging.debug("{count} emails sent to {receiver}."
                      .format(count=len(links_by_message_body.keys()), receiver=receiver))
    return seen


def get_report(listing, head=None, exclude_links=False):
    description = listing.description

    # Only report the first n lines of the description if head is specified
    if head:
        description = '\n'.join(listing.description.strip().split('\n')[:head])

    link_formatted = '{link}\n'.format(link=listing.link) if not exclude_links else ''

    listing_formatted = ('*' * 25 + '\n'
                                    '{link_formatted}'
                                    '{listing.title}\n'
                                    '${listing.price} - {listing.age} - '
                                    '{listing.city}, {listing.state}\n'
                                    '*  {description}\n\n'.format(**locals()))

    # Kill non-ascii characters
    return listing_formatted.encode('ascii', 'ignore').decode()


def create_message_bodies(search_term, listings, char_limit=None, head=None, exclude_links=False):
    report_by_listing = {}
    # Format listings
    for listing in listings:
        report_by_listing[listing] = get_report(listing, head, exclude_links)

    header = HEADER_TEMPLATE.format(plural="es" if len(listings) > 1 else "", query=search_term)
    subject = SUBJECT_TEMPLATE.format(query=search_term,
                                      n=len(listings),
                                      total=len(listings),
                                      time=get_time())

    links_by_message_body = {}
    links = []
    listings_report = ""

    # If there's a character limit, break the report into parts so that no part exceeds char_limit.
    for listing, report in report_by_listing.items():
        if char_limit:
            # If listing pushes message body past character count, store message body without adding the listing.
            # Note: Subject is included in char count since it's included in the message body when sent as SMS.
            if len(listings_report) + len(report) + len(header) + len(subject) > char_limit:
                links_by_message_body[BODY_TEMPLATE.format(header=header, listings_report=listings_report)] = links
                listings_report = ""
                links = []

        links.append(listing.link)
        listings_report += report

    if len(report_by_listing) > 0:
        links_by_message_body[BODY_TEMPLATE.format(header=header, listings_report=listings_report)] = links

    return links_by_message_body


def get_time():
    return datetime.datetime.now().strftime("%H:%M")


def main(args):
    # Set up logging
    logfile = args.pop('logfile')
    if logfile:
        logging.basicConfig(filename=logfile, filemode='w',
                            format=('%(asctime)s %(module)s %(levelname)s'
                                    ': %(message)s'),
                            datefmt='%m/%d/%Y %I:%M:%S %p', )
    loglevel = args.pop('loglevel')
    if loglevel:
        numeric_level = getattr(logging, loglevel.upper(), None)
        if not isinstance(numeric_level, int):
            raise ValueError('Invalid log level: %s' % loglevel)
        logging.getLogger().setLevel(numeric_level)

    # Get needed controls
    minutes = args.pop('time')
    loop_delay = minutes * 60

    # Dictionary to store results of queries
    load_file = args.pop("load")
    seen = io.load_dict(load_file) if load_file else {}

    sender = args.pop('email', None)
    smtpserver = args.pop('smtpserver', None)
    if not sender:
        sender = input("Enter email address to use: ")
    if not smtpserver:
        smtpserver = EmailSession.get_smtp(sender)
    passwd = getpass.getpass("Enter password for sending email from {email}: ".format(email=sender))

    EmailSession.test_email_login(sender, passwd, smtpserver)

    receiver = args.pop('receiver', None)
    if not receiver:
        receiver = sender

    exception_receiver = "your email"
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

    save_file = args.pop("save")

    # find our results
    queries = args.pop('query')
    exception_thresh = 5 * 10
    exception_count = 0
    today = None

    while True:
        try:
            logging.debug("Checking KSL")
            seen = check_ksl(args, queries, seen, receiver, sender, passwd, smtpserver)
            # log seen list daily for debug
            if today != datetime.date.today():
                logging.debug("seen list: %s" % (seen))
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
                    message = MESSAGE_TEMPLATE.format(subject="KSL Notifier Failure",
                                                      receiver=exception_receiver, sender=sender,
                                                      body="Exception in script detected.\n" \
                                                           "Exception count %d\n" \
                                                           "The script will die after the count reaches 10\n" \
                                                           "%s" % (exception_count / 10, exc_txt))

                    with EmailSession(sender, passwd, smtpserver) as email_session:
                        logging.info("Sending exception message to {receiver}".format(receiver=exception_receiver))
                        email_session.sendmail(sender, exception_receiver, message)
            except e:
                logging.debug(
                    "There was an issue sending the exception message to {sender}. {e}".format(sender=sender, e=e))
            # If there is something more basic failing, the count trigger
            # a final failure of the loop.
            if exception_count > 100:
                logging.error("Too many exceptions, terminating")
                raise
        finally:
            if save_file:
                io.save_dict(save_file, seen)
            logging.debug("Exception count is {count}".format(count=exception_count / 10))

        logging.debug("Sleeping for {minutes} minutes".format(minutes=minutes))
        time.sleep(loop_delay)


if __name__ == '__main__':
    args = KslNotifyCli().parser.parse_args()

    main(vars(args))
