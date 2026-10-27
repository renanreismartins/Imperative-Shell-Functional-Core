import logging

from margin_call.margin_call import process_margin_call

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    process_margin_call("ACC-123")
