import argparse
import logging
import sys
from pathlib import Path

from whatsapp_kb.bot import KnowledgeBot


def _config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="config.yaml", type=Path)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="whatsapp-kb")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve")
    _config_argument(serve)

    reindex = commands.add_parser("reindex")
    _config_argument(reindex)
    reindex.add_argument("--force", action="store_true")

    ask = commands.add_parser("ask")
    _config_argument(ask)
    ask.add_argument("question")

    pending = commands.add_parser("pending")
    _config_argument(pending)
    pending.add_argument("--done", type=int)

    unpause = commands.add_parser("unpause")
    _config_argument(unpause)
    unpause.add_argument("sender")

    args = parser.parse_args(argv)
    bot = KnowledgeBot.open(args.config)
    if args.command == "serve":
        bot.serve()
        return 0
    if args.command == "reindex":
        count = bot.reindex(force=args.force)
        print(count)
        return 0
    if args.command == "ask":
        bot.reindex()
        outcome = bot.answer(args.question)
        print(outcome.text)
        return 0
    if args.command == "unpause":
        bot.unpause(args.sender)
        return 0
    if args.done is not None:
        if not bot.resolve_pending(args.done):
            print("No está en la lista.", file=sys.stderr)
            return 1
        return 0
    for item in bot.pending():
        print(f"{item.id}\t{item.created_at}\t{item.sender}\t{item.question}")
    return 0
