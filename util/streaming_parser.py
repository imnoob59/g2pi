import json
from typing import Iterator, Dict, Any, Iterable, AsyncIterator
from itertools import chain

def parse_json_array_stream(line_iterator: Iterable[str]) -> Iterator[Dict[str, Any]]:
    """
    Parse stream array JSON yang diformat (pretty-printed) yang terdiri dari baris teks.

    Fungsi ini adalah generator, yang akan untuk setiap objek JSON level pertama yang ditemukan di stream
    menghasilkan (yield) dictionary Python lengkap. Tujuan desainnya adalah efisiensi memori tinggi,
    ，。

    Args:
        line_iterator: 。，`requests.Response.iter_lines()`
                       。

    Yields:
        JSON。

    Raises:
        ValueError: JSON，
                    。
    """
    # 
    buffer = []
    brace_level = 0
    in_array = False

    # 1.  '['，
    for line in line_iterator:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line.startswith('['):
            in_array = True
            #  '[' ，
            line = stripped_line[1:]
            #  chain ，（）
            line_iterator = chain([line], line_iterator)
            break
    
    if not in_array:
        raise ValueError("JSON ( '[' ) 。")

    # 2. ，
    in_string = False  # 
    escape_next = False  # 

    for line in line_iterator:
        for char in line:
            # 
            if escape_next:
                if brace_level > 0:
                    buffer.append(char)
                escape_next = False
                continue

            # 
            if char == '\\':
                if brace_level > 0:
                    buffer.append(char)
                escape_next = True
                continue

            # （）
            if char == '"' and brace_level > 0:
                in_string = not in_string
                buffer.append(char)
                continue

            # ，
            if not in_string:
                #  '{' ，
                if char == '{':
                    # ，，
                    if brace_level == 0:
                        buffer = []
                    brace_level += 1

                #  (brace_level > 0)，
                if brace_level > 0:
                    buffer.append(char)

                #  '}' ，
                if char == '}':
                    brace_level -= 1
                    # 0，
                    if brace_level == 0 and buffer:
                        obj_str = "".join(buffer)
                        try:
                            # 
                            #  strict=False 
                            yield json.loads(obj_str, strict=False)
                        except json.JSONDecodeError as e:
                            # ，
                            raise ValueError(f"JSON: {e}\n: {obj_str}") from e
                        finally:
                            # ，
                            buffer = []
                            in_string = False  # 
            else:
                # ，
                if brace_level > 0:
                    buffer.append(char)

    # 3. ，
    if brace_level != 0:
        print(f": JSON， {brace_level}，。")

async def parse_json_array_stream_async(line_iterator: AsyncIterator[str]) -> AsyncIterator[Dict[str, Any]]:
    """
    ：Parse stream array JSON yang diformat (pretty-printed) yang terdiri dari baris teks.

    Generator，JSON
    menghasilkan (yield) dictionary Python lengkap. Tujuan desainnya adalah efisiensi memori tinggi,
    ，。

    Args:
        line_iterator: 。，`httpx.Response.aiter_lines()`

    Yields:
        JSON。

    Raises:
        ValueError: JSON，
                    。
    """
    # 
    buffer = []
    brace_level = 0
    in_array = False

    # 1.  '['，
    in_string = False
    escape_next = False

    async for line in line_iterator:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line.startswith('['):
            in_array = True
            #  '[' ，
            line = stripped_line[1:]
            # （）
            for char in line:
                if escape_next:
                    if brace_level > 0:
                        buffer.append(char)
                    escape_next = False
                    continue

                if char == '\\':
                    if brace_level > 0:
                        buffer.append(char)
                    escape_next = True
                    continue

                if char == '"' and brace_level > 0:
                    in_string = not in_string
                    buffer.append(char)
                    continue

                if not in_string:
                    if char == '{':
                        if brace_level == 0:
                            buffer = []
                        brace_level += 1

                    if brace_level > 0:
                        buffer.append(char)

                    if char == '}':
                        brace_level -= 1
                        if brace_level == 0 and buffer:
                            obj_str = "".join(buffer)
                            try:
                                yield json.loads(obj_str, strict=False)
                            except json.JSONDecodeError as e:
                                raise ValueError(f"JSON: {e}\n: {obj_str}") from e
                            finally:
                                buffer = []
                                in_string = False
                else:
                    if brace_level > 0:
                        buffer.append(char)
            break

    if not in_array:
        raise ValueError("JSON ( '[' ) 。")

    # 2. ，（）
    async for line in line_iterator:
        for char in line:
            # 
            if escape_next:
                if brace_level > 0:
                    buffer.append(char)
                escape_next = False
                continue

            # 
            if char == '\\':
                if brace_level > 0:
                    buffer.append(char)
                escape_next = True
                continue

            # （）
            if char == '"' and brace_level > 0:
                in_string = not in_string
                buffer.append(char)
                continue

            # ，
            if not in_string:
                #  '{' ，
                if char == '{':
                    # ，，
                    if brace_level == 0:
                        buffer = []
                    brace_level += 1

                #  (brace_level > 0)，
                if brace_level > 0:
                    buffer.append(char)

                #  '}' ，
                if char == '}':
                    brace_level -= 1
                    # 0，
                    if brace_level == 0 and buffer:
                        obj_str = "".join(buffer)
                        try:
                            # 
                            #  strict=False 
                            yield json.loads(obj_str, strict=False)
                        except json.JSONDecodeError as e:
                            # ，
                            raise ValueError(f"JSON: {e}\n: {obj_str}") from e
                        finally:
                            # ，
                            buffer = []
                            in_string = False  # 
            else:
                # ，
                if brace_level > 0:
                    buffer.append(char)

    # 3. ，
    if brace_level != 0:
        print(f": JSON， {brace_level}，。")

