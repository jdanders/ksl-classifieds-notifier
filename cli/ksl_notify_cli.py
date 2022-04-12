from cli.ksl_cli import KslCli


class KslNotifyCli(KslCli):
    def __init__(self):
        super().__init__()
        self.parser.description = 'ksl_notify - command line utility to notify of new KSL classifieds ads'

        self.parser.add_argument('--email', default=None,
                                 help='email address to send emails from. ' 
                                      'If --to-email is not specified, this email will also be used as the receiver of the email.')
        self.parser.add_argument('--to-email', default=None,
                                 help='email address to send the email to. Defaults to --email value.')
        self.parser.add_argument('--exception-email', default=None,
                                 help='email address to send exception emails to. Defaults to --email value.')
        self.parser.add_argument('--smtpserver', default='',
                                 help='email SMTP server:port, should be unneeded for '
                                      'gmail, outlook, hotmail, msn, yahoo, or comcast')
        self.parser.add_argument('-t', '--time', nargs='?', default=10, const=int, type=int,
                                 help='Number of minutes to wait between searches')
        self.parser.add_argument('-H', '--head', default=None, type=int,
                                 help="Number of lines to include from the listing's description. "
                                      "If not specified, the entire description will be included.")
        self.parser.add_argument('-C', '--char-limit', default=None, type=int,
                                 help="Number of characters allowed in the message body. "
                                      "Listings that exceed the character count will be sent in additional messages.")
        self.parser.add_argument('-X', '--exclude-links', default=False, action='store_true',
                                 help='Exclude links from message.')
        self.parser.add_argument('-L', '--load', default=None,
                                 help='Load seen listings from a JSON file. ' 
                                      'Format is a dictionary of query search terms to listing links.')
        self.parser.add_argument('-S', '--save', default=None,
                                 help='Save seen listings to a JSON file.')
        self.parser.add_argument('-l', '--logfile', default=None,
                                 help='File to log output from daemon process, defaults to stdout')
        self.parser.add_argument('--loglevel', default="INFO",
                                 help='Choose level: debug, info, warning')
        self.parser.add_argument('-f', '--foreground', action='store_const', default=0, const=1,
                                 help='Do not fork to background')
        self.parser.add_argument('-e', '--email-exceptions', default='5',
                                 help='Number of repeated exceptions before sending emails')