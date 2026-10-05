"""Minimal terminal entry point; gameplay and training commands are not implemented."""

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Adaptive heads-up poker bot skeleton.")
    parser.parse_args()
    print("Project skeleton ready. Training and gameplay are not implemented yet.")


if __name__ == "__main__":
    main()
