"""CLI: train crop classifier and yield regressor."""

import logging

from agri_sense.models.train import train_all


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    train_all()


if __name__ == "__main__":
    main()
