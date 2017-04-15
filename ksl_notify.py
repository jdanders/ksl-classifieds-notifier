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
subject = "{query} search match on KSL Classifieds"
sender = "KSL Notify <{mail}>"
message_template = "\r\n".join([
    "Subject: {subject}",
    "To: {email}",
    "From: {sender}",
    "",
    "New match{plural} found for query {query}"
    "",
    "{report}"])


def get_smtp(email):
    # Maybe there's a service or library that does this?
    hostname = email.split("@", 1)[-1]
    if hostname == 'gmail.com':
        smtp_server = 'smtp.gmail.com:587'
    elif hostname == 'yahoo.com':
        smtp_server = 'smtp.mail.yahoo.com:587'
    elif hostname == 'outlook.com' or hostname == 'hotmail.com':
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


def send_email(email, password, smtpserver, report, query, count):
    smtp_addr, smtp_port = smtpserver.split(":")
    smtp = smtplib.SMTP(smtp_addr, int(smtp_port))
    smtp.ehlo()
    smtp.starttls()
    smtp.login(email, password)
    if count > 1:
        plural = "es"
    else:
        plural = ""
    body = message_template.format(subject=subject.format(query=query),
                                   email=email,
                                   sender=sender.format(mail=email),
                                   plural=plural, query=query, report=report)
    smtp.sendmail(sender.format(mail=email), email, body)
    smtp.quit()
    logging.debug("Sent this body:\n{body}".format(body=body))


def gather_report(query_result, seen):
    report = ""
    new_seen = seen.copy()
    for result in query_result:
        if result.link not in seen:
            report += ('*' * 25 +
                       '\n{result.link}\n'
                       '{result.title}\n'
                       '{result.price} - {result.age} - '
                       '{result.city}, {result.state}\n'
                       '*  {result.description}\n\n'.format(**locals()))
            # Kill non-ascii characters
            new_seen.append(result.link)
    return report, new_seen


def check_ksl(args, queries, seen, email, passwd, smtpserver):
    # create the thin object
    ksl = KSL()
    for query, html_data in ksl.search(queries, **args):
        if query not in seen:
            seen[query] = []

        query_result = ksl.find_elements(html_data)
        report, new_seen_list = gather_report(query_result, seen[query])
        # If any new content, email results
        if report:
            count = len(new_seen_list) - len(seen[query])
            logging.info("Sending email")
            send_email(email, passwd, smtpserver, report, query, count)

        # Save of results for next time
        seen[query] = new_seen_list
    return seen


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
    email = args.pop('email', None)
    smtpserver = args.pop('smtpserver', None)
    if not email:
        email = input("Enter email address to use: ")
    if not smtpserver:
        smtpserver = get_smtp(email)
    passwd = getpass.getpass("Enter password for sending email from {email}: "
                             .format(email=email))
    test_email_login(email, passwd, smtpserver)

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
    exception_count = 0
    today = None
    while True:
        try:
            seen = check_ksl(args, queries, seen, email, passwd, smtpserver)
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
        except:
            logging.exception("Exception found in main loop")
            exception_count += 10
            try:
                send_email(email, passwd, smtpserver, str(queries),
                           "Exception in script detected.\n"
                           "Exception count %d\n"
                           "The script will die after the count reaches 10"
                           % (exception_count / 10), 0)
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
                   help='email address from which to both send and receive')
    p.add_argument('--smtpserver', default='',
                   help='email SMTP server:port, should be unneeded for '
                   'gmail, outlook, hotmail, yahoo, or comcast')
    p.add_argument('-t', '--time', nargs='?', default=10, const=int,
                   help='Number of minutes to wait between searches')
    p.add_argument('-l', '--logfile', default=None,
                   help='File to log output from daemon process, defaults '
                   'to stdout')
    p.add_argument('--loglevel', default="INFO",
                   help='Choose level: debug, info, warning')
    p.add_argument('query', nargs='+', action='store', default=None,
                   help='List of terms to search on KSL classifieds. '
                   'Use quotes for multiword searches')
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

    args = p.parse_args()

    main(vars(args))
