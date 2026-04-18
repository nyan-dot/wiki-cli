from .ingest import (
    import_sep_command,
    register_import_sep_parser,
    register_seed_note_parser,
    register_seed_person_parser,
    seed_note_command,
    seed_person_command,
)
from .maintenance import (
    build_index_command,
    lint_wiki_command,
    list_pages_command,
    register_build_index_parser,
    register_lint_parser,
    register_list_pages_parser,
)
from .workspace import init_command, register_init_parser

COMMAND_PARSER_REGISTRARS = [
    register_init_parser,
    register_import_sep_parser,
    register_seed_note_parser,
    register_seed_person_parser,
    register_list_pages_parser,
    register_build_index_parser,
    register_lint_parser,
]

__all__ = [
    "COMMAND_PARSER_REGISTRARS",
    "build_index_command",
    "import_sep_command",
    "init_command",
    "lint_wiki_command",
    "list_pages_command",
    "register_build_index_parser",
    "register_import_sep_parser",
    "register_init_parser",
    "register_lint_parser",
    "register_list_pages_parser",
    "register_seed_note_parser",
    "register_seed_person_parser",
    "seed_note_command",
    "seed_person_command",
]
