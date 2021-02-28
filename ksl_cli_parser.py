import argparse


class KslCliParser(object):
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description='ksl - command line utility to query KSL classifieds'
        )

        self.parser.add_argument('query', nargs='+', action='store', default=None,
                                 help='List of terms to search on KSL classifieds. '
                                      'Use quotes for multiword searches')
        self.parser.add_argument('-x', '--expand-search', action='store_const', default=0, const=1,
                                 help='Include listings more broadly related to your search terms.')
        self.parser.add_argument('-c', '--category', default=None,
                                 help='Category to apply to search results')
        self.parser.add_argument('-u', '--subcategory', default=None, dest='subCategory',
                                 help='Category to apply to search results')
        self.parser.add_argument('-m', '--min-price', default='0',
                                 help='Minimum dollar amount to include in search results')
        self.parser.add_argument('-M', '--max-price', default='0',
                                 help='Maximum dollar amount to include in search results')
        self.parser.add_argument('-z', '--zip', default=None,
                                 help='ZIP code around which to center search results')
        self.parser.add_argument('--city', default=None,
                                 help='City around which to center search results')
        self.parser.add_argument('--state', default=None,
                                 help='State (abbr, like UT) around which to center search '
                                      'results')
        self.parser.add_argument('-d', '--miles', default=None,
                                 help='Maximum distance in miles from ZIP code center')
        self.parser.add_argument('-n', '--perPage', default=None,
                                 help='Number of results to include in search results.'
                                      '(Does not seem to work!)')
        self.parser.add_argument('-r', '--reverse', action='store_const',
                                 default=0, const=1, dest='sort',
                                 help='If included, query will sort oldest to newest. '
                                      'Default is newest to oldest')
        self.parser.add_argument('-s', '--sold', action='store_const', default=0, const=1,
                                 help='If included, query will return results for sold '
                                      'items as well as active items')
