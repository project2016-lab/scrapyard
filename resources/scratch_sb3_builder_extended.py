#!/usr/bin/env python3
"""A small, dependency-free Scratch 3 (.sb3) project builder and validator."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
import json
import random
import string
import zipfile
from pathlib import Path
from typing import Any


def _id(length: int = 20) -> str:
    """Return an alphanumeric identifier suitable for Scratch block/variable IDs."""
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _literal(value: Any, kind: int | None = None) -> list[Any]:
    """Encode a literal in Scratch's primitive-input format."""
    if kind is None:
        if isinstance(value, bool):
            kind = 8
        elif isinstance(value, (int, float)):
            kind = 4
        else:
            kind = 10
    # Scratch stores primitive values as strings in project.json.
    if isinstance(value, bool):
        value = str(value).lower()
    return [kind, str(value)]


# Block metadata consolidated from the uploaded Scratch VM source files.
# These describe how to serialize blocks; they do not embed the VM's JavaScript
# implementations into an .sb3 project.
def _spec(kind: str, inputs: dict[str, str] | None = None,
          fields: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"kind": kind, "inputs": inputs or {}, "fields": list(fields)}


BLOCK_CATALOG: dict[str, dict[str, Any]] = {}


def _register(opcode: str, kind: str, inputs: dict[str, str] | None = None,
              fields: tuple[str, ...] = ()) -> None:
    BLOCK_CATALOG[opcode] = _spec(kind, inputs, fields)


# Motion blocks (scratch3_motion.js)
for _op, _kind, _inputs, _fields in [
    ("motion_movesteps", "command", {"STEPS": "number"}, ()),
    ("motion_gotoxy", "command", {"X": "number", "Y": "number"}, ()),
    ("motion_goto", "command", {"TO": "menu"}, ()),
    ("motion_turnright", "command", {"DEGREES": "number"}, ()),
    ("motion_turnleft", "command", {"DEGREES": "number"}, ()),
    ("motion_pointindirection", "command", {"DIRECTION": "number"}, ()),
    ("motion_pointtowards", "command", {"TOWARDS": "menu"}, ()),
    ("motion_glidesecstoxy", "command", {"SECS": "number", "X": "number", "Y": "number"}, ()),
    ("motion_glideto", "command", {"SECS": "number", "TO": "menu"}, ()),
    ("motion_ifonedgebounce", "command", {}, ()),
    ("motion_setrotationstyle", "command", {}, ("STYLE",)),
    ("motion_changexby", "command", {"DX": "number"}, ()),
    ("motion_setx", "command", {"X": "number"}, ()),
    ("motion_changeyby", "command", {"DY": "number"}, ()),
    ("motion_sety", "command", {"Y": "number"}, ()),
    ("motion_xposition", "reporter", {}, ()),
    ("motion_yposition", "reporter", {}, ()),
    ("motion_direction", "reporter", {}, ()),
    ("motion_scroll_right", "command", {}, ()),
    ("motion_scroll_up", "command", {}, ()),
    ("motion_align_scene", "command", {}, ()),
    ("motion_xscroll", "reporter", {}, ()),
    ("motion_yscroll", "reporter", {}, ()),
]: _register(_op, _kind, _inputs, _fields)

# Looks blocks (scratch3_looks.js)
for _op, _kind, _inputs, _fields in [
    ("looks_say", "command", {"MESSAGE": "text"}, ()),
    ("looks_sayforsecs", "command", {"MESSAGE": "text", "SECS": "number"}, ()),
    ("looks_think", "command", {"MESSAGE": "text"}, ()),
    ("looks_thinkforsecs", "command", {"MESSAGE": "text", "SECS": "number"}, ()),
    ("looks_show", "command", {}, ()),
    ("looks_hide", "command", {}, ()),
    ("looks_hideallsprites", "command", {}, ()),
    ("looks_switchcostumeto", "command", {"COSTUME": "menu"}, ()),
    ("looks_switchbackdropto", "command", {"BACKDROP": "menu"}, ()),
    ("looks_switchbackdroptoandwait", "command", {"BACKDROP": "menu"}, ()),
    ("looks_nextcostume", "command", {}, ()),
    ("looks_nextbackdrop", "command", {}, ()),
    ("looks_changeeffectby", "command", {"CHANGE": "number"}, ("EFFECT",)),
    ("looks_seteffectto", "command", {"VALUE": "number"}, ("EFFECT",)),
    ("looks_cleargraphiceffects", "command", {}, ()),
    ("looks_changesizeby", "command", {"CHANGE": "number"}, ()),
    ("looks_setsizeto", "command", {"SIZE": "number"}, ()),
    ("looks_changestretchby", "command", {"CHANGE": "number"}, ()),
    ("looks_setstretchto", "command", {"STRETCH": "number"}, ()),
    ("looks_gotofrontback", "command", {}, ("FRONT_BACK",)),
    ("looks_goforwardbackwardlayers", "command", {"NUM": "number"}, ("FORWARD_BACKWARD",)),
    ("looks_size", "reporter", {}, ()),
    ("looks_costumenumbername", "reporter", {}, ("NUMBER_NAME",)),
    ("looks_backdropnumbername", "reporter", {}, ("NUMBER_NAME",)),
]: _register(_op, _kind, _inputs, _fields)

# Event blocks, including hats handled by the VM scheduler rather than a primitive.
for _op, _kind, _inputs, _fields in [
    ("event_whenflagclicked", "hat", {}, ()),
    ("event_whenkeypressed", "hat", {}, ("KEY_OPTION",)),
    ("event_whenthisspriteclicked", "hat", {}, ()),
    ("event_whenstageclicked", "hat", {}, ()),
    ("event_whenbackdropswitchesto", "hat", {}, ("BACKDROP",)),
    ("event_whenbroadcastreceived", "hat", {}, ("BROADCAST_OPTION",)),
    ("event_whentouchingobject", "hat", {"TOUCHINGOBJECTMENU": "menu"}, ()),
    ("event_broadcast", "command", {"BROADCAST_OPTION": "menu"}, ()),
    ("event_broadcastandwait", "command", {"BROADCAST_OPTION": "menu"}, ()),
    ("event_whengreaterthan", "hat", {"VALUE": "number"}, ("WHENGREATERTHANMENU",)),
]: _register(_op, _kind, _inputs, _fields)

# Data / variable / list blocks (scratch3_data.js)
for _op, _kind, _inputs, _fields in [
    ("data_variable", "reporter", {}, ("VARIABLE",)),
    ("data_setvariableto", "command", {"VALUE": "any"}, ("VARIABLE",)),
    ("data_changevariableby", "command", {"VALUE": "number"}, ("VARIABLE",)),
    ("data_hidevariable", "command", {}, ("VARIABLE",)),
    ("data_showvariable", "command", {}, ("VARIABLE",)),
    ("data_listcontents", "reporter", {}, ("LIST",)),
    ("data_addtolist", "command", {"ITEM": "any"}, ("LIST",)),
    ("data_deleteoflist", "command", {"INDEX": "any"}, ("LIST",)),
    ("data_deletealloflist", "command", {}, ("LIST",)),
    ("data_insertatlist", "command", {"ITEM": "any", "INDEX": "any"}, ("LIST",)),
    ("data_replaceitemoflist", "command", {"ITEM": "any", "INDEX": "any"}, ("LIST",)),
    ("data_itemoflist", "reporter", {"INDEX": "any"}, ("LIST",)),
    ("data_itemnumoflist", "reporter", {"ITEM": "any"}, ("LIST",)),
    ("data_lengthoflist", "reporter", {}, ("LIST",)),
    ("data_listcontainsitem", "boolean", {"ITEM": "any"}, ("LIST",)),
    ("data_hidelist", "command", {}, ("LIST",)),
    ("data_showlist", "command", {}, ("LIST",)),
]: _register(_op, _kind, _inputs, _fields)

# Control blocks (scratch3_control.js)
for _op, _kind, _inputs, _fields in [
    ("control_repeat", "command", {"TIMES": "number", "SUBSTACK": "substack"}, ()),
    ("control_repeat_until", "command", {"CONDITION": "boolean", "SUBSTACK": "substack"}, ()),
    ("control_while", "command", {"CONDITION": "boolean", "SUBSTACK": "substack"}, ()),
    ("control_for_each", "command", {"VALUE": "number", "SUBSTACK": "substack"}, ("VARIABLE",)),
    ("control_forever", "command", {"SUBSTACK": "substack"}, ()),
    ("control_wait", "command", {"DURATION": "number"}, ()),
    ("control_wait_until", "command", {"CONDITION": "boolean"}, ()),
    ("control_if", "command", {"CONDITION": "boolean", "SUBSTACK": "substack"}, ()),
    ("control_if_else", "command", {"CONDITION": "boolean", "SUBSTACK": "substack", "SUBSTACK2": "substack"}, ()),
    ("control_stop", "command", {}, ("STOP_OPTION",)),
    ("control_create_clone_of", "command", {"CLONE_OPTION": "menu"}, ()),
    ("control_delete_this_clone", "command", {}, ()),
    ("control_get_counter", "reporter", {}, ()),
    ("control_incr_counter", "command", {}, ()),
    ("control_clear_counter", "command", {}, ()),
    ("control_all_at_once", "command", {"SUBSTACK": "substack"}, ()),
    ("control_start_as_clone", "hat", {}, ()),
]: _register(_op, _kind, _inputs, _fields)

# Operators (scratch3_operators.js)
for _op, _kind, _inputs, _fields in [
    ("operator_add", "reporter", {"NUM1": "number", "NUM2": "number"}, ()),
    ("operator_subtract", "reporter", {"NUM1": "number", "NUM2": "number"}, ()),
    ("operator_multiply", "reporter", {"NUM1": "number", "NUM2": "number"}, ()),
    ("operator_divide", "reporter", {"NUM1": "number", "NUM2": "number"}, ()),
    ("operator_lt", "boolean", {"OPERAND1": "any", "OPERAND2": "any"}, ()),
    ("operator_equals", "boolean", {"OPERAND1": "any", "OPERAND2": "any"}, ()),
    ("operator_gt", "boolean", {"OPERAND1": "any", "OPERAND2": "any"}, ()),
    ("operator_and", "boolean", {"OPERAND1": "boolean", "OPERAND2": "boolean"}, ()),
    ("operator_or", "boolean", {"OPERAND1": "boolean", "OPERAND2": "boolean"}, ()),
    ("operator_not", "boolean", {"OPERAND": "boolean"}, ()),
    ("operator_random", "reporter", {"FROM": "number", "TO": "number"}, ()),
    ("operator_join", "reporter", {"STRING1": "text", "STRING2": "text"}, ()),
    ("operator_letter_of", "reporter", {"LETTER": "number", "STRING": "text"}, ()),
    ("operator_length", "reporter", {"STRING": "text"}, ()),
    ("operator_contains", "boolean", {"STRING1": "text", "STRING2": "text"}, ()),
    ("operator_mod", "reporter", {"NUM1": "number", "NUM2": "number"}, ()),
    ("operator_round", "reporter", {"NUM": "number"}, ()),
    ("operator_mathop", "reporter", {"NUM": "number"}, ("OPERATOR",)),
]: _register(_op, _kind, _inputs, _fields)

# Sensing blocks (scratch3_sensing.js)
for _op, _kind, _inputs, _fields in [
    ("sensing_touchingobject", "boolean", {"TOUCHINGOBJECTMENU": "menu"}, ()),
    ("sensing_touchingcolor", "boolean", {"COLOR": "color"}, ()),
    ("sensing_coloristouchingcolor", "boolean", {"COLOR": "color", "COLOR2": "color"}, ()),
    ("sensing_distanceto", "reporter", {"DISTANCETOMENU": "menu"}, ()),
    ("sensing_timer", "reporter", {}, ()),
    ("sensing_resettimer", "command", {}, ()),
    ("sensing_of", "reporter", {"OBJECT": "menu"}, ("PROPERTY",)),
    ("sensing_mousex", "reporter", {}, ()),
    ("sensing_mousey", "reporter", {}, ()),
    ("sensing_setdragmode", "command", {}, ("DRAG_MODE",)),
    ("sensing_mousedown", "boolean", {}, ()),
    ("sensing_keypressed", "boolean", {"KEY_OPTION": "menu"}, ()),
    ("sensing_current", "reporter", {}, ("CURRENTMENU",)),
    ("sensing_dayssince2000", "reporter", {}, ()),
    ("sensing_loudness", "reporter", {}, ()),
    ("sensing_loud", "boolean", {}, ()),
    ("sensing_askandwait", "command", {"QUESTION": "text"}, ()),
    ("sensing_answer", "reporter", {}, ()),
    ("sensing_username", "reporter", {}, ()),
    ("sensing_userid", "reporter", {}, ()),
]: _register(_op, _kind, _inputs, _fields)

# Custom procedures have dynamic inputs. Their raw mutation / input data is passed through.
for _op, _kind, _inputs, _fields in [
    ("procedures_definition", "procedure", {"custom_block": "shadow"}, ()),
    ("procedures_call", "procedure", {}, ()),
    ("argument_reporter_string_number", "reporter", {}, ("VALUE",)),
    ("argument_reporter_boolean", "boolean", {}, ("VALUE",)),
    ("procedures_prototype", "shadow", {}, ()),
]: _register(_op, _kind, _inputs, _fields)

# Common menu shadow opcodes paired with their parent input.
MENU_INPUTS: dict[tuple[str, str], tuple[str, str]] = {
    ("motion_goto", "TO"): ("motion_goto_menu", "TO"),
    ("motion_glideto", "TO"): ("motion_glideto_menu", "TO"),
    ("motion_pointtowards", "TOWARDS"): ("motion_pointtowards_menu", "TOWARDS"),
    ("looks_switchcostumeto", "COSTUME"): ("looks_costume", "COSTUME"),
    ("looks_switchbackdropto", "BACKDROP"): ("looks_backdrops", "BACKDROP"),
    ("looks_switchbackdroptoandwait", "BACKDROP"): ("looks_backdrops", "BACKDROP"),
    ("event_whentouchingobject", "TOUCHINGOBJECTMENU"): ("event_touchingobjectmenu", "TOUCHINGOBJECTMENU"),
    ("event_broadcast", "BROADCAST_OPTION"): ("event_broadcast_menu", "BROADCAST_OPTION"),
    ("event_broadcastandwait", "BROADCAST_OPTION"): ("event_broadcast_menu", "BROADCAST_OPTION"),
    ("sensing_touchingobject", "TOUCHINGOBJECTMENU"): ("sensing_touchingobjectmenu", "TOUCHINGOBJECTMENU"),
    ("sensing_distanceto", "DISTANCETOMENU"): ("sensing_distancetomenu", "DISTANCETOMENU"),
    ("sensing_of", "OBJECT"): ("sensing_of_object_menu", "OBJECT"),
    ("sensing_keypressed", "KEY_OPTION"): ("sensing_keyoptions", "KEY_OPTION"),
    ("control_create_clone_of", "CLONE_OPTION"): ("control_create_clone_of_menu", "CLONE_OPTION"),
}
for _menu_opcode, _field in {
    "motion_goto_menu": "TO", "motion_glideto_menu": "TO",
    "motion_pointtowards_menu": "TOWARDS", "looks_costume": "COSTUME",
    "looks_backdrops": "BACKDROP", "event_touchingobjectmenu": "TOUCHINGOBJECTMENU",
    "event_broadcast_menu": "BROADCAST_OPTION", "sensing_touchingobjectmenu": "TOUCHINGOBJECTMENU",
    "sensing_distancetomenu": "DISTANCETOMENU", "sensing_of_object_menu": "OBJECT",
    "sensing_keyoptions": "KEY_OPTION", "control_create_clone_of_menu": "CLONE_OPTION",
}.items():
    _register(_menu_opcode, "menu", {}, (_field,))


@dataclass(frozen=True)
class BlockInput:
    """Reference to a block nested in another block's input.

    Set input_type to Scratch's serialized input kind (usually 3 for a value
    reporter, 2 for a Boolean/statement-style connection). A fallback can be a
    Scratch primitive tuple such as [4, "10"].
    """
    block_id: str
    input_type: int | None = None
    fallback: Any = None


class Block:
    """A convenient representation of one Scratch block."""

    def __init__(
        self,
        opcode: str,
        *,
        shadow: bool = False,
        top_level: bool = False,
        x: int | float | None = None,
        y: int | float | None = None,
        inputs: dict[str, Any] | None = None,
        fields: dict[str, Any] | None = None,
        mutation: dict[str, Any] | None = None,
    ) -> None:
        self.id = _id()
        self.data: dict[str, Any] = {
            "opcode": opcode,
            "next": None,
            "parent": None,
            "inputs": inputs or {},
            "fields": fields or {},
            "shadow": bool(shadow),
            "topLevel": bool(top_level),
        }
        if top_level:
            self.data["x"] = 0 if x is None else x
            self.data["y"] = 0 if y is None else y
        if mutation is not None:
            self.data["mutation"] = mutation


class Target:
    """A Scratch stage or sprite target."""

    def __init__(self, name: str, *, is_stage: bool = False) -> None:
        self.name = name
        self.data: dict[str, Any] = {
            "isStage": is_stage,
            "name": name,
            "variables": {},
            "lists": {},
            "broadcasts": {},
            "blocks": {},
            "comments": {},
            "currentCostume": 0,
            "costumes": [],
            "sounds": [],
            "volume": 100,
            "layerOrder": 1,
        }
        if is_stage:
            self.data.update(
                {
                    "tempo": 60,
                    "videoTransparency": 50,
                    "videoState": "off",
                    "textToSpeechLanguage": None,
                }
            )
        else:
            self.data.update(
                {
                    "visible": True,
                    "x": 0,
                    "y": 0,
                    "size": 100,
                    "direction": 90,
                    "draggable": False,
                    "rotationStyle": "all around",
                }
            )

    def _put_block(self, block: Block) -> str:
        self.data["blocks"][block.id] = block.data
        return block.id

    def add_block(
        self,
        opcode: str,
        *,
        inputs: dict[str, Any] | None = None,
        fields: dict[str, Any] | None = None,
        shadow: bool = False,
        top_level: bool = False,
        x: int | float = 0,
        y: int | float = 0,
        mutation: dict[str, Any] | None = None,
    ) -> str:
        return self._put_block(
            Block(
                opcode,
                shadow=shadow,
                top_level=top_level,
                x=x,
                y=y,
                inputs=inputs,
                fields=fields,
                mutation=mutation,
            )
        )

    def chain(self, *block_ids: str) -> str | None:
        """Connect existing blocks into a normal stack and return its first ID."""
        if not block_ids:
            return None

        for block_id in block_ids:
            if block_id not in self.data["blocks"]:
                raise ValueError(f"Unknown block id: {block_id}")

        for index, block_id in enumerate(block_ids):
            block = self.data["blocks"][block_id]
            block["next"] = block_ids[index + 1] if index + 1 < len(block_ids) else None
            block["parent"] = block_ids[index - 1] if index else None

        first = self.data["blocks"][block_ids[0]]
        first["topLevel"] = True
        first.setdefault("x", 0)
        first.setdefault("y", 0)

        for block_id in block_ids[1:]:
            block = self.data["blocks"][block_id]
            block["topLevel"] = False
            block.pop("x", None)
            block.pop("y", None)

        return block_ids[0]

    def add_stack(self, opcode_list: list[str], *, x: int | float = 0, y: int | float = 0) -> str | None:
        block_ids = [
            self.add_block(opcode, top_level=(index == 0), x=x, y=y)
            for index, opcode in enumerate(opcode_list)
        ]
        return self.chain(*block_ids)

    def variable(self, name: str, value: Any = 0, *, cloud: bool = False) -> str:
        variable_id = _id()
        self.data["variables"][variable_id] = [name, value, True] if cloud else [name, value]
        return variable_id

    def list(self, name: str, values: list[Any] | None = None) -> str:
        list_id = _id()
        self.data["lists"][list_id] = [name, list(values or [])]
        return list_id

    def broadcast(self, name: str) -> str:
        broadcast_id = _id()
        self.data["broadcasts"][broadcast_id] = name
        return broadcast_id

    @staticmethod
    def literal_input(value: Any, kind: int | None = None) -> list[Any]:
        """Return a Scratch serialized value input, e.g. [1, [4, "10"]]."""
        return [1, _literal(value, kind)]

    @staticmethod
    def field_value(value: Any, field_id: str | None = None) -> list[Any]:
        """Encode a Scratch field as [display_value, referenced_id_or_null]."""
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return [value[0], value[1]]
        return [str(value).lower() if isinstance(value, bool) else str(value), field_id]

    def _encode_catalog_field(self, name: str, value: Any) -> list[Any]:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return [value[0], value[1]]
        if name == "VARIABLE":
            for variable_id, variable in self.data["variables"].items():
                if variable and variable[0] == value:
                    return [str(value), variable_id]
        elif name == "LIST":
            for list_id, list_data in self.data["lists"].items():
                if list_data and list_data[0] == value:
                    return [str(value), list_id]
        elif name == "BROADCAST_OPTION":
            for broadcast_id, broadcast_name in self.data["broadcasts"].items():
                if broadcast_name == value:
                    return [str(value), broadcast_id]
        return self.field_value(value)

    def connect_input(
        self,
        parent_id: str,
        input_name: str,
        child_id: str,
        *,
        input_type: int = 3,
        fallback: Any = None,
    ) -> None:
        """Connect an existing reporter/menu/other block to a parent input.

        ``fallback`` is an optional serialized shadow primitive or shadow block
        reference to preserve the input's default value.
        """
        blocks = self.data["blocks"]
        if parent_id not in blocks or child_id not in blocks:
            raise ValueError("parent_id and child_id must refer to blocks on this target")
        connection: list[Any] = [input_type, child_id]
        if fallback is not None:
            connection.append(copy.deepcopy(fallback))
        blocks[parent_id].setdefault("inputs", {})[input_name] = connection
        child = blocks[child_id]
        child["parent"] = parent_id
        child["topLevel"] = False
        child.pop("x", None)
        child.pop("y", None)

    def connect_substack(self, parent_id: str, input_name: str, first_block_id: str) -> None:
        """Connect the first block of a stack to SUBSTACK or SUBSTACK2."""
        self.connect_input(parent_id, input_name, first_block_id, input_type=2)

    def add_menu_input(
        self,
        parent_id: str,
        input_name: str,
        menu_opcode: str,
        field_name: str,
        value: Any,
        *,
        field_id: str | None = None,
    ) -> str:
        """Create and attach a menu shadow block to a parent input."""
        if menu_opcode not in BLOCK_CATALOG:
            raise ValueError(f"Menu opcode is not in BLOCK_CATALOG: {menu_opcode}")
        menu_id = self.add_block(
            menu_opcode,
            fields={field_name: self.field_value(value, field_id)},
            shadow=True,
        )
        self.connect_input(parent_id, input_name, menu_id, input_type=1)
        return menu_id

    def add_catalog_block(
        self,
        opcode: str,
        *,
        values: dict[str, Any] | None = None,
        fields: dict[str, Any] | None = None,
        input_blocks: dict[str, str | BlockInput] | None = None,
        substacks: dict[str, str] | None = None,
        menus: dict[str, Any] | None = None,
        raw_inputs: dict[str, Any] | None = None,
        mutation: dict[str, Any] | None = None,
        shadow: bool = False,
        top_level: bool | None = None,
        x: int | float = 0,
        y: int | float = 0,
    ) -> str:
        """Build a known Scratch block using the uploaded-source block catalog.

        ``values`` fills primitive inputs, ``fields`` fills dropdown/variable
        fields, ``input_blocks`` attaches reporters/Boolean blocks, ``substacks``
        attaches statement stacks, and ``menus`` selects menu values. For block
        forms with unusual serialization (especially custom procedures),
        supply ``raw_inputs`` and/or ``mutation`` directly.
        """
        spec = BLOCK_CATALOG.get(opcode)
        if spec is None:
            raise ValueError(
                f"Unsupported catalog opcode {opcode!r}. Use add_block() for a custom/unknown opcode."
            )
        if top_level is None:
            top_level = spec["kind"] == "hat"
        values = dict(values or {})
        encoded_fields = {
            name: self._encode_catalog_field(name, value)
            for name, value in (fields or {}).items()
        }
        encoded_inputs: dict[str, Any] = copy.deepcopy(raw_inputs or {})
        menu_values = dict(menus or {})

        for input_name, value in values.items():
            input_kind = spec["inputs"].get(input_name)
            if input_kind is None:
                raise ValueError(f"{opcode} has no catalog input named {input_name!r}")
            if input_kind in ("reporter", "boolean", "substack"):
                raise ValueError(
                    f"{opcode}.{input_name} expects a connected block; use input_blocks or substacks"
                )
            if input_kind == "menu":
                menu_values[input_name] = value
                continue
            literal_kind = {"number": 4, "text": 10, "color": 9}.get(input_kind)
            encoded_inputs[input_name] = [1, _literal(value, literal_kind)]

        # Add the parent block first so attached input blocks can reference it.
        block_id = self.add_block(
            opcode,
            inputs=encoded_inputs,
            fields=encoded_fields,
            shadow=shadow,
            top_level=top_level,
            x=x,
            y=y,
            mutation=mutation,
        )

        for input_name, raw_value in menu_values.items():
            menu_def = MENU_INPUTS.get((opcode, input_name))
            if menu_def is None:
                raise ValueError(
                    f"No known menu shadow definition for {opcode}.{input_name}; pass it in raw_inputs instead"
                )
            menu_opcode, menu_field = menu_def
            # Preserve a caller-supplied (display_value, ID) tuple for broadcasts.
            if isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
                menu_value, menu_id = raw_value[0], raw_value[1]
            else:
                menu_value, menu_id = raw_value, None
                if menu_field in ("VARIABLE", "LIST", "BROADCAST_OPTION"):
                    found = self._encode_catalog_field(menu_field, raw_value)
                    menu_value, menu_id = found[0], found[1]
            self.add_menu_input(
                block_id, input_name, menu_opcode, menu_field, menu_value, field_id=menu_id
            )

        for input_name, ref in (input_blocks or {}).items():
            input_kind = spec["inputs"].get(input_name)
            if input_kind is None:
                raise ValueError(f"{opcode} has no catalog input named {input_name!r}")
            if isinstance(ref, BlockInput):
                child_id = ref.block_id
                input_type = ref.input_type
                fallback = ref.fallback
            else:
                child_id = ref
                input_type = 1 if input_kind == "shadow" else (2 if input_kind == "boolean" else 3)
                fallback = None
                if input_kind in ("number", "any"):
                    fallback = [4, "0"]
                elif input_kind == "text":
                    fallback = [10, ""]
                elif input_kind == "color":
                    fallback = [9, "#000000"]
            self.connect_input(
                block_id,
                input_name,
                child_id,
                input_type=input_type if input_type is not None else (1 if input_kind == "shadow" else (2 if input_kind == "boolean" else 3)),
                fallback=fallback,
            )

        for input_name, first_id in (substacks or {}).items():
            if spec["inputs"].get(input_name) != "substack":
                raise ValueError(f"{opcode}.{input_name} is not a catalog substack input")
            self.connect_substack(block_id, input_name, first_id)

        return block_id

    def add_costume(
        self,
        name: str,
        asset_id: str,
        *,
        data_format: str = "svg",
        rotation_center_x: int | float = 240,
        rotation_center_y: int | float = 180,
        md5ext: str | None = None,
    ) -> None:
        if md5ext is None:
            md5ext = f"{asset_id}.{data_format}"
        self.data["costumes"].append(
            {
                "name": name,
                "dataFormat": data_format,
                "assetId": asset_id,
                "md5ext": md5ext,
                "rotationCenterX": rotation_center_x,
                "rotationCenterY": rotation_center_y,
            }
        )

    def add_sound(
        self,
        name: str,
        asset_id: str,
        *,
        data_format: str = "wav",
        rate: int = 48000,
        sample_count: int = 0,
        md5ext: str | None = None,
    ) -> None:
        if md5ext is None:
            md5ext = f"{asset_id}.{data_format}"
        self.data["sounds"].append(
            {
                "name": name,
                "assetId": asset_id,
                "dataFormat": data_format,
                "format": "",
                "rate": rate,
                "sampleCount": sample_count,
                "md5ext": md5ext,
            }
        )

    # Integrated target script helpers
    def add_when_flag(self, x: int | float = 0, y: int | float = 0) -> str:
        return self.add_block("event_whenflagclicked", top_level=True, x=x, y=y)

    def add_say(self, message: Any, seconds: int | float | None = None) -> str:
        if seconds is None:
            return self.add_block("looks_say", inputs={"MESSAGE": [1, _literal(message)]})
        return self.add_block(
            "looks_sayforsecs",
            inputs={
                "MESSAGE": [1, _literal(message)],
                "SECS": [1, _literal(seconds, 4)],
            },
        )

    def add_move(self, steps: int | float) -> str:
        return self.add_block("motion_movesteps", inputs={"STEPS": [1, _literal(steps, 4)]})


class ScratchProject:
    """Scratch 3 project builder with a catalog for the uploaded core block sources."""

    def __init__(self, *, stage_name: str = "Stage", vm: str = "15.1.1") -> None:
        self.targets: list[Target] = []
        self.extensions: list[str] = []
        self.meta = {"semver": "3.0.0", "vm": vm, "agent": "scratch_sb3_builder"}
        self.assets: dict[str, bytes] = {}
        self.stage = self.add_target(stage_name, is_stage=True)
        self._ensure_default_costume(self.stage)

    def _ensure_default_costume(self, target: Target) -> None:
        if target.data.get("costumes"):
            return

        if target.data.get("isStage"):
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360">'
                '<rect width="480" height="360" fill="white"/></svg>'
            )
            name, center_x, center_y = "backdrop1", 240, 180
        else:
            svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                '<circle cx="50" cy="50" r="40" fill="#4c97ff"/></svg>'
            )
            name, center_x, center_y = "costume1", 50, 50

        asset_id = hashlib.md5(svg.encode("utf-8")).hexdigest()
        filename = f"{asset_id}.svg"
        self.assets[filename] = svg.encode("utf-8")
        target.add_costume(
            name,
            asset_id,
            data_format="svg",
            rotation_center_x=center_x,
            rotation_center_y=center_y,
            md5ext=filename,
        )

    def add_target(self, name: str, *, is_stage: bool = False) -> Target:
        target = Target(name, is_stage=is_stage)
        # Keep layer orders positive and distinct, as expected by SB3 validators.
        target.data["layerOrder"] = len(self.targets) + 1
        self.targets.append(target)
        return target

    def add_sprite(self, name: str) -> Target:
        sprite = self.add_target(name, is_stage=False)
        self._ensure_default_costume(sprite)
        return sprite

    def to_json(self) -> dict[str, Any]:
        return {
            "targets": [copy.deepcopy(target.data) for target in self.targets],
            "monitors": [],
            "extensions": list(self.extensions),
            "meta": dict(self.meta),
        }

    @staticmethod
    def supported_block_opcodes() -> list[str]:
        """Return sorted catalog opcodes gathered from the uploaded VM files."""
        return sorted(BLOCK_CATALOG)

    def validate(self) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        target_names: set[str] = set()

        for target in self.targets:
            if target.name in target_names:
                errors.append(f"Duplicate target name: {target.name}")
            target_names.add(target.name)

            data = target.data
            if not isinstance(data.get("blocks"), dict):
                errors.append(f"{target.name}: blocks must be an object")
                continue

            blocks = data["blocks"]
            for block_id, block in blocks.items():
                # Scratch also uses certain array entries for comments in some project variants.
                if isinstance(block, list):
                    if block and block[0] in (12, 13):
                        continue
                    warnings.append(f"{target.name}: non-block array entry {block_id} ignored")
                    continue
                if not isinstance(block, dict):
                    errors.append(f"{target.name}: block {block_id} is not an object")
                    continue

                for ref_name in ("next", "parent"):
                    ref = block.get(ref_name)
                    if ref is not None and ref not in blocks:
                        errors.append(
                            f"{target.name}: block {block_id} has missing {ref_name} reference {ref}"
                        )

                inputs = block.get("inputs", {})
                if not isinstance(inputs, dict):
                    errors.append(f"{target.name}: block {block_id} inputs must be an object")
                    continue
                for input_name, value in inputs.items():
                    if not isinstance(value, list) or len(value) < 2:
                        errors.append(
                            f"{target.name}: block {block_id} input {input_name} is malformed"
                        )
                        continue
                    candidate = value[1]
                    if isinstance(candidate, str) and candidate not in blocks:
                        errors.append(
                            f"{target.name}: block {block_id} input {input_name} references missing block {candidate}"
                        )
                    elif isinstance(candidate, list) and len(candidate) >= 2:
                        nested = candidate[1]
                        # A string in a primitive tuple is a literal, not necessarily a block ID.
                        if isinstance(nested, str) and candidate[0] in (1, 2, 3):
                            if nested not in blocks:
                                errors.append(
                                    f"{target.name}: block {block_id} input {input_name} references missing block {nested}"
                                )

                if block.get("topLevel"):
                    if "x" not in block or "y" not in block:
                        errors.append(f"{target.name}: top-level block {block_id} lacks x/y")
                elif "x" in block or "y" in block:
                    warnings.append(f"{target.name}: non-top-level block {block_id} has x/y")

            for block_id, block in blocks.items():
                if not isinstance(block, dict):
                    continue
                next_id = block.get("next")
                next_block = blocks.get(next_id) if next_id is not None else None
                if isinstance(next_block, dict) and next_block.get("parent") != block_id:
                    errors.append(
                        f"{target.name}: {block_id}.next={next_id}, but "
                        f"{next_id}.parent is {next_block.get('parent')}"
                    )

            if not data.get("costumes"):
                errors.append(f"{target.name}: target has no costumes")

        if not self.targets:
            errors.append("Project has no targets")
        else:
            stage_count = sum(bool(target.data.get("isStage")) for target in self.targets)
            if stage_count == 0:
                errors.append("Project has no Stage target")
            elif stage_count != 1:
                errors.append("Project must have exactly one Stage target")

        return errors, warnings

    def save_sb3(self, path: str | Path, *, assets_dir: str | Path | None = None) -> list[str]:
        """Validate and write the project and its assets to an .sb3 ZIP archive."""
        errors, warnings = self.validate()
        if errors:
            raise ValueError("Project validation failed:\n- " + "\n- ".join(errors))

        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        asset_directory = Path(assets_dir) if assets_dir is not None else None
        written_names: set[str] = set()

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "project.json",
                json.dumps(self.to_json(), separators=(",", ":"), ensure_ascii=False),
            )
            written_names.add("project.json")

            for filename, asset_data in self.assets.items():
                archive.writestr(filename, asset_data)
                written_names.add(filename)

            if asset_directory is not None:
                for target in self.targets:
                    for asset_group in ("costumes", "sounds"):
                        for item in target.data.get(asset_group, []):
                            filename = item.get("md5ext")
                            if (
                                filename
                                and filename not in written_names
                                and (asset_directory / filename).is_file()
                            ):
                                archive.write(asset_directory / filename, filename)
                                written_names.add(filename)

        return warnings


def main() -> None:
    """Create a small example project when this file is run directly."""
    project = ScratchProject()
    player = project.add_sprite("Player")

    start = player.add_when_flag(50, 50)
    move = player.add_move(15)
    say = player.add_say("Hello World!")
    player.chain(start, move, say)

    output_path = Path("output_fixed.sb3")
    warnings = project.save_sb3(output_path)
    print(f"Project successfully created: {output_path.resolve()}")
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
