"""Trusted P05 blocked-ticket fixture construction and committed-blob validation."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from academy_engine.command import GitCommandError, run_git


class P05FixtureError(ValueError):
    """The trusted P05 blocked-summary fixture is absent or not exact."""


P05_BLOCKED_TICKET_ID = "RQ-105"
P05_BLOCKED_TICKET_REASON = "Venue access is awaiting facilities clearance"
_FIXTURE_PATHS = (
    "tests/test_cli.py",
    "workshop_queue/cli.py",
    "workshop_queue/model.py",
    "workshop_queue/service.py",
)
_OVERLAY_PATH = "training_scenarios/P05-checkpoint-remediation.json"
_OVERLAY_SOURCE = "academy/scenarios/P05-checkpoint-remediation/files/scenario.json"
_DEFECT = "sum(ticket.status in {TicketStatus.OPEN, TicketStatus.CLAIMED} for ticket in tickets)"
_CORRECT = "sum(ticket.status is not TicketStatus.COMPLETED for ticket in tickets)"


def _decode(raw: bytes, path: str) -> str:
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw or not raw.endswith(b"\n"):
        raise P05FixtureError(f"P05 fixture source is not canonical: {path}")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise P05FixtureError(f"P05 fixture source is not UTF-8: {path}") from error


def _blob(repository: Path, ref: str, path: str) -> bytes | None:
    result = run_git(repository, ["show", f"{ref}:{path}"], check=False, trust_local_config=True)
    return result.stdout.encode("utf-8", "surrogateescape") if result.returncode == 0 else None


def _replace(text: str, old: str, new: str, path: str) -> str:
    if text.count(old) != 1:
        raise P05FixtureError(f"P05 fixture source is not exact: {path}")
    return text.replace(old, new)


def _definition(tree: ast.Module, name: str, *, class_name: str | None = None) -> ast.FunctionDef | None:
    body = tree.body
    if class_name is not None:
        owner = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name), None)
        body = owner.body if owner is not None else []
    return next((node for node in body if isinstance(node, ast.FunctionDef) and node.name == name), None)


def _self_call(node: ast.AST, name: str, arguments: tuple[str, ...]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr == name
        and not node.keywords
        and tuple(argument.value for argument in node.args if isinstance(argument, ast.Constant) and isinstance(argument.value, str)) == arguments
        and len(node.args) == len(arguments)
    )


def _json_loads_result(node: ast.AST, result: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "json"
        and node.func.attr == "loads"
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Attribute)
        and isinstance(node.args[0].value, ast.Name)
        and node.args[0].value.id == result
        and node.args[0].attr == "stdout"
    )


def _subscript_key(node: ast.AST, key: str, parsed: set[str], result: str) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == key
        and (
            (isinstance(node.value, ast.Name) and node.value.id in parsed)
            or _json_loads_result(node.value, result)
        )
    )


def _fixture_setup_precedes(body: tuple[ast.stmt, ...], command_indexes: tuple[int, ...]) -> bool:
    """Require the direct, persisted RQ-105 setup before any lifecycle command."""
    if not command_indexes:
        return False

    def fixture_read(statement: ast.stmt) -> bool:
        if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
            return False
        load = statement.value
        if not (
            len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id == "tickets"
            and isinstance(load.func, ast.Attribute)
            and isinstance(load.func.value, ast.Name)
            and load.func.value.id == "json"
            and load.func.attr == "loads"
            and len(load.args) == 1
        ):
            return False
        read = load.args[0]
        return (
            isinstance(read, ast.Call)
            and isinstance(read.func, ast.Attribute)
            and isinstance(read.func.value, ast.Attribute)
            and isinstance(read.func.value.value, ast.Name)
            and read.func.value.value.id == "self"
            and read.func.value.attr == "fixture"
            and read.func.attr == "read_text"
            and not read.args
            and len(read.keywords) == 1
            and read.keywords[0].arg == "encoding"
            and isinstance(read.keywords[0].value, ast.Constant)
            and read.keywords[0].value.value == "utf-8"
        )

    def ticket_id(statement: ast.stmt) -> bool:
        target = statement.targets[0] if isinstance(statement, ast.Assign) and len(statement.targets) == 1 else None
        return (
            isinstance(target, ast.Subscript)
            and isinstance(target.slice, ast.Constant)
            and target.slice.value == "id"
            and isinstance(target.value, ast.Subscript)
            and isinstance(target.value.value, ast.Name)
            and target.value.value.id == "tickets"
            and isinstance(target.value.slice, ast.Constant)
            and target.value.slice.value == 0
            and isinstance(statement.value, ast.Constant)
            and statement.value.value == P05_BLOCKED_TICKET_ID
        )

    def fixture_write(statement: ast.stmt) -> bool:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            return False
        write = statement.value
        if not (
            isinstance(write.func, ast.Attribute)
            and isinstance(write.func.value, ast.Attribute)
            and isinstance(write.func.value.value, ast.Name)
            and write.func.value.value.id == "self"
            and write.func.value.attr == "fixture"
            and write.func.attr == "write_text"
            and len(write.args) == 1
            and len(write.keywords) == 1
            and write.keywords[0].arg == "encoding"
            and isinstance(write.keywords[0].value, ast.Constant)
            and write.keywords[0].value.value == "utf-8"
        ):
            return False
        dump = write.args[0]
        return (
            isinstance(dump, ast.Call)
            and isinstance(dump.func, ast.Attribute)
            and isinstance(dump.func.value, ast.Name)
            and dump.func.value.id == "json"
            and dump.func.attr == "dumps"
            and len(dump.args) == 1
            and isinstance(dump.args[0], ast.Name)
            and dump.args[0].id == "tickets"
            and not dump.keywords
        )

    setup_indexes = (
        tuple(index for index, statement in enumerate(body) if fixture_read(statement)),
        tuple(index for index, statement in enumerate(body) if ticket_id(statement)),
        tuple(index for index, statement in enumerate(body) if fixture_write(statement)),
    )
    return all(indexes for indexes in setup_indexes) and max(indexes[0] for indexes in setup_indexes) < min(command_indexes)


def _test_contract(tree: ast.Module) -> bool:
    function = _definition(tree, "test_p05_prepared_blocked_ticket_persists_before_summary_defect", class_name="WorkshopQueueCliTests")
    if function is None:
        return False
    body = tuple(function.body)
    assignments = {
        statement.targets[0].id: statement.value
        for statement in body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    }
    commands = {
        "claim_result": ("claim", "RQ-105", "--volunteer", "Sam"),
        "block_result": ("block", "RQ-105", "--reason", P05_BLOCKED_TICKET_REASON),
        "report_result": ("report", "--format", "json"),
        "list_result": ("list", "--format", "json"),
    }
    if not all(_self_call(assignments.get(result), "run_cli", command) for result, command in commands.items()):
        return False
    command_indexes = tuple(
        index
        for index, statement in enumerate(body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id in commands
    )
    if not _fixture_setup_precedes(body, command_indexes):
        return False
    parsed_report = {name for name, value in assignments.items() if _json_loads_result(value, "report_result")}
    # Compare structure rather than object identity because these AST nodes were parsed independently.
    def success(statement: ast.stmt, result: str) -> bool:
        return (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "self"
            and statement.value.func.attr == "assertEqual"
            and len(statement.value.args) >= 2
            and isinstance(statement.value.args[0], ast.Attribute)
            and isinstance(statement.value.args[0].value, ast.Name)
            and statement.value.args[0].value.id == result
            and statement.value.args[0].attr == "returncode"
            and isinstance(statement.value.args[1], ast.Constant)
            and statement.value.args[1].value == 0
        )
    if not all(any(success(statement, result) for statement in body) for result in commands):
        return False
    report_assertions = {
        key: any(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "self"
            and statement.value.func.attr == "assertEqual"
            and len(statement.value.args) >= 2
            and _subscript_key(statement.value.args[0], key, parsed_report, "report_result")
            and isinstance(statement.value.args[1], ast.Constant)
            and statement.value.args[1].value == expected
            for statement in body
        )
        for key, expected in (("blocked", 1), ("unresolved", 0))
    }
    persisted = assignments.get("persisted")
    persisted_lifecycle = (
        isinstance(persisted, ast.Call)
        and isinstance(persisted.func, ast.Name)
        and persisted.func.id == "next"
        and any(
            _json_loads_result(node, "list_result")
            for node in ast.walk(persisted)
        )
        and any(isinstance(node, ast.Constant) and node.value == P05_BLOCKED_TICKET_ID for node in ast.walk(persisted))
    )
    def persisted_assertion(field: str, expected: object | None, assertion: str) -> bool:
        return any(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "self"
            and statement.value.func.attr == assertion
            and bool(statement.value.args)
            and _subscript_key(statement.value.args[0], field, {"persisted"}, "list_result")
            and (
                assertion == "assertIsNotNone"
                or (len(statement.value.args) >= 2 and isinstance(statement.value.args[1], ast.Constant) and statement.value.args[1].value == expected)
            )
            for statement in body
        )
    return (
        all(report_assertions.values())
        and persisted_lifecycle
        and persisted_assertion("blocked_at", None, "assertIsNotNone")
        and persisted_assertion("blocked_reason", P05_BLOCKED_TICKET_REASON, "assertEqual")
    )


def _fixture_contract(tree: ast.Module, blobs: dict[str, str]) -> bool:
    model = ast.parse(blobs["workshop_queue/model.py"], filename="workshop_queue/model.py")
    service = ast.parse(blobs["workshop_queue/service.py"], filename="workshop_queue/service.py")
    cli = ast.parse(blobs["workshop_queue/cli.py"], filename="workshop_queue/cli.py")
    tests = ast.parse(blobs["tests/test_cli.py"], filename="tests/test_cli.py")
    status = next((node for node in model.body if isinstance(node, ast.ClassDef) and node.name == "TicketStatus"), None)
    ticket = next((node for node in model.body if isinstance(node, ast.ClassDef) and node.name == "Ticket"), None)
    if status is None or ticket is None:
        return False
    members = {
        node.targets[0].id: node.value.value
        for node in status.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    fields = {
        node.target.id
        for node in ticket.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    post_init = _definition(model, "__post_init__", class_name="Ticket")
    from_mapping = _definition(model, "from_mapping", class_name="Ticket")
    block_ticket = _definition(service, "block_ticket")
    parser = _definition(cli, "_build_parser")
    main = _definition(cli, "main")
    report = _definition(cli, "_write_report")
    if (
        members.get("BLOCKED") != "blocked"
        or not {"blocked_at", "blocked_reason"}.issubset(fields)
        or post_init is None
        or from_mapping is None
        or block_ticket is None
        or parser is None
        or main is None
        or report is None
        or not _test_contract(tests)
    ):
        return False
    model_names = {node.attr for node in ast.walk(post_init) if isinstance(node, ast.Attribute)}
    mapping_keywords = {node.arg for node in ast.walk(from_mapping) if isinstance(node, ast.keyword)}
    def blocked_transition(statement: ast.stmt) -> bool:
        if not isinstance(statement, ast.Return) or not isinstance(statement.value, ast.Call):
            return False
        replacement = statement.value
        if not isinstance(replacement.func, ast.Name) or replacement.func.id != "_replace_ticket" or len(replacement.args) != 3:
            return False
        if not all(isinstance(argument, ast.Name) for argument in replacement.args[:2]) or [argument.id for argument in replacement.args[:2]] != ["tickets", "ticket_id"]:
            return False
        ticket_replace = replacement.args[2]
        if not isinstance(ticket_replace, ast.Call) or not isinstance(ticket_replace.func, ast.Name) or ticket_replace.func.id != "replace":
            return False
        if len(ticket_replace.args) != 1 or not isinstance(ticket_replace.args[0], ast.Name) or ticket_replace.args[0].id != "ticket":
            return False
        keywords = {keyword.arg: keyword.value for keyword in ticket_replace.keywords}
        return (
            isinstance(keywords.get("status"), ast.Attribute)
            and isinstance(keywords["status"].value, ast.Name)
            and keywords["status"].value.id == "TicketStatus"
            and keywords["status"].attr == "BLOCKED"
            and isinstance(keywords.get("blocked_at"), ast.Name)
            and keywords["blocked_at"].id == "now"
            and isinstance(keywords.get("blocked_reason"), ast.Name)
            and keywords["blocked_reason"].id == "reason"
        )

    def claimed_guard(statement: ast.stmt) -> bool:
        return (
            isinstance(statement, ast.If)
            and isinstance(statement.test, ast.Compare)
            and len(statement.test.ops) == 1
            and isinstance(statement.test.ops[0], ast.IsNot)
            and isinstance(statement.test.left, ast.Attribute)
            and isinstance(statement.test.left.value, ast.Name)
            and statement.test.left.value.id == "ticket"
            and statement.test.left.attr == "status"
            and len(statement.test.comparators) == 1
            and isinstance(statement.test.comparators[0], ast.Attribute)
            and isinstance(statement.test.comparators[0].value, ast.Name)
            and statement.test.comparators[0].value.id == "TicketStatus"
            and statement.test.comparators[0].attr == "CLAIMED"
            and any(
                isinstance(child, ast.Raise)
                and isinstance(child.exc, ast.Call)
                and isinstance(child.exc.func, ast.Name)
                and child.exc.func.id == "InvalidTransition"
                for child in statement.body
            )
        )

    lifecycle = any(
        isinstance(loop, ast.For)
        and isinstance(loop.target, ast.Name)
        and loop.target.id == "ticket"
        and isinstance(loop.iter, ast.Name)
        and loop.iter.id == "tickets"
        and any(
            isinstance(match, ast.If)
            and isinstance(match.test, ast.Compare)
            and len(match.test.ops) == 1
            and isinstance(match.test.ops[0], ast.Eq)
            and isinstance(match.test.left, ast.Attribute)
            and isinstance(match.test.left.value, ast.Name)
            and match.test.left.value.id == "ticket"
            and match.test.left.attr == "ticket_id"
            and len(match.test.comparators) == 1
            and isinstance(match.test.comparators[0], ast.Name)
            and match.test.comparators[0].id == "ticket_id"
            and any(claimed_guard(statement) for statement in match.body)
            and any(blocked_transition(statement) for statement in match.body)
            for match in loop.body
        )
        for loop in block_ticket.body
    )
    parser_assignments = {
        statement.targets[0].id: statement.value
        for statement in parser.body
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
    }
    block_parser = parser_assignments.get("block_parser")
    parser_contract = (
        isinstance(block_parser, ast.Call)
        and isinstance(block_parser.func, ast.Attribute)
        and isinstance(block_parser.func.value, ast.Name)
        and block_parser.func.value.id == "commands"
        and block_parser.func.attr == "add_parser"
        and len(block_parser.args) == 1
        and isinstance(block_parser.args[0], ast.Constant)
        and block_parser.args[0].value == "block"
        and all(
            any(
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and isinstance(statement.value.func, ast.Attribute)
                and isinstance(statement.value.func.value, ast.Name)
                and statement.value.func.value.id == "block_parser"
                and statement.value.func.attr == "add_argument"
                and bool(statement.value.args)
                and isinstance(statement.value.args[0], ast.Constant)
                and statement.value.args[0].value == argument
                and (
                    argument != "--reason"
                    or any(keyword.arg == "required" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in statement.value.keywords)
                )
                for statement in parser.body
            )
            for argument in ("ticket_id", "--reason")
        )
    )
    def main_block_branch(node: ast.AST) -> bool:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare) or len(node.test.ops) != 1 or not isinstance(node.test.ops[0], ast.Eq):
            return False
        if not (
            isinstance(node.test.left, ast.Attribute)
            and isinstance(node.test.left.value, ast.Name)
            and node.test.left.value.id == "arguments"
            and node.test.left.attr == "command"
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "block"
        ):
            return False
        return any(
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Attribute)
            and isinstance(statement.value.func.value, ast.Name)
            and statement.value.func.value.id == "store"
            and statement.value.func.attr == "save"
            and len(statement.value.args) == 1
            and isinstance(statement.value.args[0], ast.Call)
            and isinstance(statement.value.args[0].func, ast.Name)
            and statement.value.args[0].func.id == "block_ticket"
            and len(statement.value.args[0].args) == 4
            and isinstance(statement.value.args[0].args[0], ast.Name)
            and statement.value.args[0].args[0].id == "tickets"
            and isinstance(statement.value.args[0].args[1], ast.Attribute)
            and isinstance(statement.value.args[0].args[1].value, ast.Name)
            and statement.value.args[0].args[1].value.id == "arguments"
            and statement.value.args[0].args[1].attr == "ticket_id"
            and isinstance(statement.value.args[0].args[2], ast.Attribute)
            and isinstance(statement.value.args[0].args[2].value, ast.Name)
            and statement.value.args[0].args[2].value.id == "arguments"
            and statement.value.args[0].args[2].attr == "reason"
            for statement in node.body
        )
    main_contract = any(main_block_branch(node) for node in ast.walk(main))
    report_contract = any(
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Subscript)
        and isinstance(statement.targets[0].value, ast.Name)
        and statement.targets[0].value.id == "counts"
        and isinstance(statement.targets[0].slice, ast.Constant)
        and statement.targets[0].slice.value == "unresolved"
        and ast.unparse(statement.value).replace("sum((", "sum(").replace("))", ")") == _DEFECT
        for statement in report.body
    )
    return (
        {"status", "blocked_at", "blocked_reason", "BLOCKED"}.issubset(model_names)
        and {"blocked_at", "blocked_reason"}.issubset(mapping_keywords)
        and lifecycle
        and parser_contract
        and main_contract
        and report_contract
    )


def _model_fixture(text: str) -> str:
    text = _replace(text, '    CLAIMED = "claimed"\n    COMPLETED = "completed"', '    CLAIMED = "claimed"\n    BLOCKED = "blocked"\n    COMPLETED = "completed"', "workshop_queue/model.py")
    text = _replace(text, '    resolution: str | None = None\n', '    resolution: str | None = None\n    blocked_at: datetime | None = None\n    blocked_reason: str | None = None\n', "workshop_queue/model.py")
    text = _replace(text, '("claimed_at", "completed_at")', '("claimed_at", "completed_at", "blocked_at")', "workshop_queue/model.py")
    text = _replace(text, '        if self.status is TicketStatus.OPEN and any(\n            value is not None for value in (self.claimed_by, self.claimed_at, self.completed_at, self.resolution)\n        ):', '        if self.blocked_reason is not None:\n            _required_string(self.blocked_reason, "blocked_reason")\n            if any(ord(character) < 32 or ord(character) == 127 for character in self.blocked_reason):\n                raise ValidationError("blocked_reason must not contain control characters")\n        if self.status is TicketStatus.OPEN and any(\n            value is not None for value in (self.claimed_by, self.claimed_at, self.completed_at, self.resolution, self.blocked_at, self.blocked_reason)\n        ):', "workshop_queue/model.py")
    text = _replace(text, '        if self.status is TicketStatus.CLAIMED and any(value is not None for value in (self.completed_at, self.resolution)):\n            raise ValidationError("claimed tickets cannot have completion metadata")', '        if self.status is TicketStatus.CLAIMED and any(value is not None for value in (self.completed_at, self.resolution, self.blocked_at, self.blocked_reason)):\n            raise ValidationError("claimed tickets cannot have completion metadata")\n        if self.status is TicketStatus.BLOCKED and any(value is None for value in (self.claimed_by, self.claimed_at, self.blocked_at, self.blocked_reason)):\n            raise ValidationError("blocked tickets require claim and block metadata")\n        if self.status is TicketStatus.BLOCKED and any(value is not None for value in (self.completed_at, self.resolution)):\n            raise ValidationError("blocked tickets cannot have completion metadata")', "workshop_queue/model.py")
    text = _replace(text, '        if self.status is TicketStatus.COMPLETED and any(\n            value is None for value in (self.claimed_by, self.claimed_at, self.completed_at, self.resolution)\n        ):\n            raise ValidationError("completed tickets require claim and resolution metadata")', '        if self.status is TicketStatus.COMPLETED and any(\n            value is None for value in (self.claimed_by, self.claimed_at, self.completed_at, self.resolution)\n        ):\n            raise ValidationError("completed tickets require claim and resolution metadata")\n        if self.status is TicketStatus.COMPLETED and any(value is not None for value in (self.blocked_at, self.blocked_reason)):\n            raise ValidationError("completed tickets cannot have block metadata")', "workshop_queue/model.py")
    text = _replace(text, '            resolution=value.get("resolution"),\n', '            resolution=value.get("resolution"),\n            blocked_at=_parse_utc_timestamp(value.get("blocked_at"), "blocked_at"),\n            blocked_reason=value.get("blocked_reason"),\n', "workshop_queue/model.py")
    return _replace(text, '("created_at", "claimed_at", "completed_at")', '("created_at", "claimed_at", "completed_at", "blocked_at")', "workshop_queue/model.py")


def _service_fixture(text: str) -> str:
    addition = '''\n\ndef block_ticket(tickets: Sequence[Ticket], ticket_id: str, reason: str, now: datetime) -> list[Ticket]:\n    _validate_now(now)\n    for ticket in tickets:\n        if ticket.ticket_id == ticket_id:\n            if ticket.status is not TicketStatus.CLAIMED:\n                raise InvalidTransition(f"ticket {ticket_id} is {ticket.status.value} and cannot be blocked")\n            if not reason.strip():\n                raise ValueError("reason must be non-empty")\n            if any(ord(character) < 32 or ord(character) == 127 for character in reason):\n                raise ValueError("reason must not contain control characters")\n            return _replace_ticket(\n                tickets, ticket_id, replace(ticket, status=TicketStatus.BLOCKED, blocked_at=now, blocked_reason=reason)\n            )\n    raise TicketNotFound(f"ticket {ticket_id} was not found")\n'''
    return text.rstrip("\n") + addition


def _cli_fixture(text: str) -> str:
    text = _replace(text, 'from .service import InvalidTransition, TicketNotFound, claim_ticket, complete_ticket', 'from .service import InvalidTransition, TicketNotFound, block_ticket, claim_ticket, complete_ticket', "workshop_queue/cli.py")
    text = _replace(text, '    complete_parser.add_argument("--resolution", required=True)\n', '    complete_parser.add_argument("--resolution", required=True)\n\n    block_parser = commands.add_parser("block", help="block a claimed ticket")\n    block_parser.add_argument("ticket_id")\n    block_parser.add_argument("--reason", required=True)\n', "workshop_queue/cli.py")
    text = _replace(text, '    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}\n', '    counts = {status.value: sum(ticket.status is status for ticket in tickets) for status in TicketStatus}\n    counts["unresolved"] = ' + _DEFECT + '\n', "workshop_queue/cli.py")
    return _replace(text, '        elif arguments.command == "report":', '        elif arguments.command == "block":\n            store.save(block_ticket(tickets, arguments.ticket_id, arguments.reason, datetime.now(timezone.utc)))\n        elif arguments.command == "report":', "workshop_queue/cli.py")


def _test_fixture(text: str) -> str:
    method = '''\n    def test_p05_prepared_blocked_ticket_persists_before_summary_defect(self) -> None:\n        tickets = json.loads(self.fixture.read_text(encoding="utf-8"))\n        tickets[0]["id"] = "RQ-105"\n        tickets[0]["title"] = "Confirm venue access"\n        self.fixture.write_text(json.dumps(tickets), encoding="utf-8")\n        claim_result = self.run_cli("claim", "RQ-105", "--volunteer", "Sam")\n        block_result = self.run_cli("block", "RQ-105", "--reason", "Venue access is awaiting facilities clearance")\n        report_result = self.run_cli("report", "--format", "json")\n        list_result = self.run_cli("list", "--format", "json")\n\n        self.assertEqual(claim_result.returncode, 0, claim_result.stderr)\n        self.assertEqual(block_result.returncode, 0, block_result.stderr)\n        self.assertEqual(report_result.returncode, 0, report_result.stderr)\n        self.assertEqual(list_result.returncode, 0, list_result.stderr)\n        self.assertEqual(json.loads(report_result.stdout)["blocked"], 1)\n        self.assertEqual(json.loads(report_result.stdout)["unresolved"], 0)\n        persisted = next(ticket for ticket in json.loads(list_result.stdout) if ticket["id"] == "RQ-105")\n        self.assertIsNotNone(persisted["blocked_at"])\n        self.assertEqual(persisted["blocked_reason"], "Venue access is awaiting facilities clearance")\n\n'''
    return _replace(text, '\n\nif __name__ == "__main__":', '\n' + method + 'if __name__ == "__main__":', "tests/test_cli.py")


def stage_p05_fixture(repository: Path, *, base: str) -> tuple[str, ...]:
    """Patch a P04 learner checkout into the four-path blocked-summary fixture."""
    if run_git(repository, ["rev-parse", "HEAD"], trust_local_config=True).stdout.strip() != base:
        raise P05FixtureError("P05 fixture must be staged from its declared base.")
    builders = {
        "workshop_queue/model.py": _model_fixture,
        "workshop_queue/service.py": _service_fixture,
        "workshop_queue/cli.py": _cli_fixture,
        "tests/test_cli.py": _test_fixture,
    }
    try:
        for path, builder in builders.items():
            raw = _blob(repository, base, path)
            if raw is None:
                raise P05FixtureError(f"P05 fixture source is missing: {path}")
            (repository / path).write_text(builder(_decode(raw, path)), encoding="utf-8", newline="\n")
        run_git(repository, ["add", "--", *_FIXTURE_PATHS], trust_local_config=True)
    except (OSError, GitCommandError) as error:
        raise P05FixtureError("P05 fixture could not be staged.") from error
    return _FIXTURE_PATHS


def validate_p05_fixture(repository: Path, prepared: str) -> bool:
    """Return whether *prepared* is the committed canonical P05 defect fixture."""
    parents = run_git(repository, ["rev-list", "--parents", "-n", "1", prepared], check=False, trust_local_config=True).stdout.split()
    if len(parents) != 2 or parents[0] != prepared:
        return False
    changed = tuple(run_git(repository, ["diff-tree", "--no-commit-id", "--name-only", "-r", prepared], check=False, trust_local_config=True).stdout.splitlines())
    expected = tuple(sorted((*_FIXTURE_PATHS, _OVERLAY_PATH)))
    if changed != expected:
        return False
    base = parents[1]
    overlay, source = _blob(repository, prepared, _OVERLAY_PATH), _blob(repository, base, _OVERLAY_SOURCE)
    if overlay is None or source is None or overlay != source:
        return False
    try:
        overlay_data = json.loads(_decode(overlay, _OVERLAY_PATH))
        if overlay_data != {"schema_version": 1, "lab_id": "P05-checkpoint-remediation", "operation": "finding_remediation", "target": "workshop-queue-finding", "starting_condition": "finding-open"}:
            return False
        blobs = {path: _decode(_blob(repository, prepared, path) or b"", path) for path in _FIXTURE_PATHS}
        for path in _FIXTURE_PATHS:
            ast.parse(blobs[path], filename=path)
    except (P05FixtureError, json.JSONDecodeError, SyntaxError):
        return False
    return _fixture_contract(ast.parse(blobs["tests/test_cli.py"]), blobs)
