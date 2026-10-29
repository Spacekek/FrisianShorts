# Fetch a Frisian puzzle from lidraughts and render it as a vertical short video.
# Usage: frisian-shorts [puzzle_id] [--upload]   (see --help)
import argparse
import json
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, time, timedelta
from functools import cache
from itertools import count, islice, pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

import imageio_ffmpeg
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from .youtube import upload

# video settings
WIDTH, HEIGHT, FPS = 1080, 1920, 60
ASSETS = Path(__file__).parent / "assets"
FONT_TITLE = str(ASSETS / "Nunito-Black.ttf")
FONT_BOLD = str(ASSETS / "Poppins-ExtraBold.ttf")  # side-to-play label, logo
FONT = str(ASSETS / "Poppins-SemiBold.ttf")  # credit line, square numbers
TITLE = "Find the best move!"
SLIDE_SECONDS = 0.25  # slide time per step; a multi-capture has one step per jump
STEP_PAUSE_SECONDS = 0.15  # pause between steps of the same move
THINK_SECONDS = 3.0  # countdown after the opponent's move, before the solution starts
HOLD_SECONDS = 1.0  # after each solution move
END_SECONDS = 2.0
SOUND_VOLUME = 0.25  # move/capture sounds from assets/move.ogg and assets/capture.ogg

# YouTube upload (--upload), filled in from the puzzle data: {id}, {rating}, {color}, {attempts}
UPLOADED = Path("uploaded.txt")  # puzzle ids already uploaded; --upload skips them and appends the new one
YT_TITLE = "Frisian draughts puzzle #{id}: find the best move! #shorts"
YT_DESCRIPTION = "Rated {rating}, {color} to play.\n\nPuzzle from https://lidraughts.org/training/frisian/{id}"
YT_TAGS = ["frisian draughts", "draughts", "checkers", "puzzle", "dammen", "frysk"]
PUBLISH_AT, PUBLISH_TZ = time(18, 0), ZoneInfo("Europe/Amsterdam")  # uploads go public at the next 18:00 Dutch time

# layout: board centered horizontally, kept above the bottom area the Shorts UI covers
BOARD_PX = 960
BOARD_XY = ((WIDTH - BOARD_PX) // 2, 420)
TIMER_Y = BOARD_XY[1] + BOARD_PX + 48
TIMER_START, TIMER_END = (90, 200, 120), (230, 80, 70)

# board look
SQ = BOARD_PX // 10
PAD = SQ // 6  # sprite margin so piece shadows can spill over the square edge
LIGHT, DARK, FRAME, NUMBER = (238, 220, 190), (160, 112, 72), (66, 40, 22), (196, 160, 124)
HIGHLIGHT = (255, 210, 60, 110)
PIECE = {"W": ((248, 243, 232), (184, 170, 146)), "B": ((60, 54, 52), (20, 16, 16))}  # face, rim
CROWN = (240, 190, 50)


def fetch_puzzle(puzzle_id=None):
    path = f"{puzzle_id}/load" if puzzle_id else "new"
    req = urllib.request.Request(
        f"https://lidraughts.org/training/frisian/{path}",
        headers={"X-Requested-With": "XMLHttpRequest", "User-Agent": "FrisianShorts"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def read_uploaded(path=UPLOADED):
    """Puzzle ids listed in the uploaded file: one per line, '#' starts a comment."""
    ids = set()
    for line in path.read_text().splitlines():
        if line := line.split("#")[0].strip():
            ids.add(int(line))
    return ids


def next_puzzle(done, tries=3):
    """The lowest-id puzzle not in done, skipping ids lidraughts doesn't have."""
    for pid in islice((i for i in count(1) if i not in done), tries):
        try:
            return fetch_puzzle(pid)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    raise SystemExit(f"no puzzle found in {tries} tries; have all puzzles been uploaded?")


def next_publish_time(now):
    """The next PUBLISH_AT in PUBLISH_TZ after now (an aware datetime): later today, else tomorrow."""
    at = datetime.combine(now.astimezone(PUBLISH_TZ).date(), PUBLISH_AT, PUBLISH_TZ)
    return at if at > now else at + timedelta(days=1)


def parse_fen(fen):
    """'W:W30,K36:B15,P42:H0:F1' -> {square: (color, role)}, role M=man K=king G/P=captured man/king."""
    pieces = {}
    for field in fen.split(":")[1:3]:
        for p in filter(None, field[1:].split(",")):
            pieces[int(p.lstrip("KGP"))] = (field[0], p[0] if p[0].isalpha() else "M")
    return pieces


def square_rc(n):
    row, i = divmod(n - 1, 5)
    return row, 2 * i + (row % 2 == 0)


def square_xy(n, flip):
    row, col = square_rc(n)
    if flip:
        row, col = 9 - row, 9 - col
    return col * SQ, row * SQ


def uci_path(uci):
    """'442404' -> [44, 24, 4]: the squares a move passes through."""
    return [int(uci[j : j + 2]) for j in range(0, len(uci), 2)]


def jumped(pieces, a, b):
    """Square of the piece strictly between a and b on a straight (diagonal or orthogonal) line, if any."""
    (ra, ca), (rb, cb) = square_rc(a), square_rc(b)
    for n in pieces:
        r, c = square_rc(n)
        if (r - ra) * (cb - ca) == (c - ca) * (rb - ra) and 0 < (r - ra) * (rb - ra) + (c - ca) * (cb - ca) < (
            rb - ra
        ) ** 2 + (cb - ca) ** 2:
            return n


@cache
def board_bg(flip):
    img = Image.new("RGB", (BOARD_PX, BOARD_PX), LIGHT)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, SQ // 6)
    for n in range(1, 51):
        x, y = square_xy(n, flip)
        d.rectangle((x, y, x + SQ - 1, y + SQ - 1), fill=DARK)
        d.text((x + 6, y + 4), str(n), font=font, fill=NUMBER)
    # wood grain: noise stretched along the rows, soft-light blended
    grain = Image.effect_noise((BOARD_PX // 24, BOARD_PX // 4), 12).resize(img.size, Image.BICUBIC)
    return ImageChops.soft_light(img, grain.convert("RGB"))


@cache
def sprite(color, role, sq=SQ):
    """A piece drawn for a square of sq pixels, with a margin of sq // 6 around it for the shadow."""
    pad = sq // 6
    ss = 4  # supersample for smooth edges
    line = round(sq * ss / 48)  # outline width, scaled with the piece
    size = (sq + 2 * pad) * ss
    c, r, depth = size / 2, sq * ss * 0.4, sq * ss * 0.05
    face, rim = PIECE[color]
    img = Image.new("RGBA", (size, size))
    d = ImageDraw.Draw(img)
    circle = lambda k, dy=0: (c - r * k, c - r * k + dy, c + r * k, c + r * k + dy)
    d.ellipse(circle(1, depth), fill=rim)  # piece thickness
    d.ellipse(circle(1), fill=face, outline=rim, width=line)
    for k in (0.74, 0.48):
        d.ellipse(circle(k), outline=rim, width=line)
    if role in "KP":
        w, h = r * 0.5, r * 0.36
        d.polygon(
            [
                (c - w, c + h),
                (c - w, c - h),
                (c - w / 2, c),
                (c, c - h * 1.3),
                (c + w / 2, c),
                (c + w, c - h),
                (c + w, c + h),
            ],
            fill=CROWN,
            outline=(150, 110, 20),
            width=line,
        )
    img = img.resize((sq + 2 * pad,) * 2, Image.LANCZOS)

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(img.getchannel("A").point(lambda a: a * 0.5).filter(ImageFilter.GaussianBlur(pad / 3)))
    out = Image.new("RGBA", img.size)
    out.alpha_composite(shadow, (pad // 4, pad // 2))
    out.alpha_composite(img)
    if role in "GP":  # captured, removed when the move completes
        out.putalpha(out.getchannel("A").point(lambda a: a * 0.35))
    return out


def draw_board(pieces, flip, highlight=(), mover=None):
    img = board_bg(flip).copy()
    d = ImageDraw.Draw(img, "RGBA")
    for n in highlight:
        x, y = square_xy(n, flip)
        d.rectangle((x, y, x + SQ - 1, y + SQ - 1), fill=HIGHLIGHT)
    for n, piece in pieces.items():
        x, y = square_xy(n, flip)
        img.paste(sprite(*piece), (x - PAD, y - PAD), sprite(*piece))
    if mover:
        x, y, piece = mover
        img.paste(sprite(*piece), (round(x) - PAD, round(y) - PAD), sprite(*piece))
    return img


def boards(data):
    """Yield (board image, seconds on screen, tag): the opponent's last move, then the solution's main line.

    tag is "move"/"capture" on the frame a piece lands (for sound), "think" for a countdown, else None.
    There's a countdown before the solver's first move and before each later one that isn't a capture.
    """
    puzzle = data["puzzle"]
    flip, solver = puzzle["color"] == "black", puzzle["color"][0].upper()
    nodes, node = [data["history"]], puzzle["branch"]
    while node:
        nodes.append(node)
        node = node["children"][0] if node["children"] else None

    pieces, side, trail = parse_fen(puzzle["fen"]), puzzle["fen"][0], []
    frame = draw_board(pieces, flip)
    yield frame, 0.5, None
    steps = round(SLIDE_SECONDS * FPS)
    for i, node in enumerate(nodes):
        path = uci_path(node["uci"])
        trail += path
        piece = pieces.pop(path[0])
        for k, (a, b) in enumerate(pairwise(path)):
            if k:
                yield frame, STEP_PAUSE_SECONDS, None
            captured = jumped(pieces, a, b)
            (x0, y0), (x1, y1) = square_xy(a, flip), square_xy(b, flip)
            for s in range(1, steps + 1):
                t = s / steps
                t = t * t * (3 - 2 * t)  # ease in-out
                frame = draw_board(pieces, flip, trail, mover=(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, piece))
                yield frame, 1 / FPS, ("move" if captured is None else "capture") if s == steps else None
            if captured is not None:
                color, role = pieces[captured]
                pieces[captured] = (color, {"M": "G", "K": "P"}.get(role, role))
                frame = draw_board(pieces, flip, trail, mover=(x1, y1, piece))
        pieces = parse_fen(node["fen"])
        frame = draw_board(pieces, flip, trail)
        if node["fen"][0] == side:  # same side still to move: lidraughts split a multi-capture over several nodes
            yield frame, STEP_PAUSE_SECONDS, None
        else:
            side, trail = node["fen"][0], []
            nxt = nodes[i + 1] if i + 1 < len(nodes) else None
            # ponytail: treats every capture as forced (captures are mandatory); a real move generator
            # would also catch a choice between captures, or a quiet move that is the only legal one
            if nxt and side == solver and (i == 0 or jumped(pieces, *uci_path(nxt["uci"])[:2]) is None):
                yield frame, THINK_SECONDS, "think"
            else:
                yield frame, HOLD_SECONDS, None
    yield frame, END_SECONDS, None


def draw_timer(frame, left):
    """Countdown bar under the board, shrinking toward the center and going from green to red."""
    img = frame.copy()
    d = ImageDraw.Draw(img, "RGBA")
    x0, x1 = BOARD_XY[0] - 22, BOARD_XY[0] + BOARD_PX + 22
    d.rounded_rectangle((x0, TIMER_Y, x1, TIMER_Y + 14), 7, fill=(255, 255, 255, 40))
    half = (x1 - x0) * left / 2
    if half > 7:
        color = tuple(round(e + (s - e) * left) for s, e in zip(TIMER_START, TIMER_END))
        d.rounded_rectangle((WIDTH / 2 - half, TIMER_Y, WIDTH / 2 + half, TIMER_Y + 14), 7, fill=color)
    return img


def add_sounds(video, sounds, out):
    """Mix a move/capture sound in at each (seconds, name); the video stream is copied, not re-encoded."""
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-y", "-loglevel", "error", "-i", video]
    for _, name in sounds:
        cmd += ["-i", str(ASSETS / f"{name}.ogg")]
    mix = "".join(f"[{i + 1}]adelay={round(t * 1000)}:all=1[s{i}];" for i, (t, _) in enumerate(sounds))
    mix += (
        "".join(f"[s{i}]" for i in range(len(sounds)))
        + f"amix=inputs={len(sounds)}:normalize=0,volume={SOUND_VOLUME}[a]"
    )
    cmd += ["-filter_complex", mix, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", out]
    subprocess.run(cmd, check=True)


def make_base(puzzle):
    base = ImageOps.fit(Image.open(ASSETS / "background.png").convert("RGB"), (WIDTH, HEIGHT))
    d = ImageDraw.Draw(base, "RGBA")
    # title: as large as fits the width, with a soft drop shadow
    size = 120
    while ImageFont.truetype(FONT_TITLE, size).getlength(TITLE) > WIDTH - 120:
        size -= 2
    font = ImageFont.truetype(FONT_TITLE, size)
    shadow = Image.new("L", base.size, 0)
    ImageDraw.Draw(shadow).text((WIDTH // 2, 158), TITLE, font=font, anchor="ma", fill=170)
    base.paste((0, 0, 0), mask=shadow.filter(ImageFilter.GaussianBlur(7)))
    d.text((WIDTH // 2, 150), TITLE, font=font, anchor="ma", fill="white")
    label_y = d.textbbox((WIDTH // 2, 150), TITLE, font=font, anchor="ma")[3] + 70

    # side to play
    text = f"{puzzle['color'].upper()} TO PLAY"
    fg, bg = ("#0b1a33", "#f8f3e8") if puzzle["color"] == "white" else ("#f8f3e8", "#1c1816")
    x0, y0, x1, y1 = d.textbbox((WIDTH // 2, label_y), text, font=ImageFont.truetype(FONT_BOLD, 40), anchor="mm")
    d.rounded_rectangle((x0 - 32, y0 - 20, x1 + 32, y1 + 20), radius=40, fill=bg)
    d.text((WIDTH // 2, label_y), text, font=ImageFont.truetype(FONT_BOLD, 40), anchor="mm", fill=fg)

    # board frame with drop shadow
    bx, by = BOARD_XY
    frame = (bx - 22, by - 22, bx + BOARD_PX + 22, by + BOARD_PX + 22)
    shadow = Image.new("L", base.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((frame[0], frame[1] + 20, frame[2], frame[3] + 20), 24, fill=180)
    base.paste((0, 0, 0), mask=shadow.filter(ImageFilter.GaussianBlur(28)))
    d.rounded_rectangle(frame, 24, fill=FRAME)

    # logo and credit under the countdown bar
    logo = Image.open(ASSETS / "logo.png")
    ly = TIMER_Y + 46
    base.paste(logo, ((WIDTH - logo.width) // 2, ly), logo)
    credit = f"Puzzle #{puzzle['id']} · rated {puzzle['rating']} · lidraughts.org"
    d.text(
        (WIDTH // 2, ly + logo.height + 22),
        credit,
        font=ImageFont.truetype(FONT, 26),
        anchor="ma",
        fill=(160, 185, 220),
    )
    return base


def main():
    parser = argparse.ArgumentParser(description="Render a lidraughts Frisian puzzle as a vertical short video.")
    parser.add_argument(
        "puzzle_id",
        nargs="?",
        type=int,
        help="puzzle to render (default: random, or with --upload the lowest id not in uploaded.txt)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="upload to YouTube, scheduled to go public at the next 18:00 Dutch time, and record the id in "
        "uploaded.txt; "
        "needs YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN",
    )
    args = parser.parse_args()
    done = read_uploaded() if args.upload else set()
    if args.puzzle_id in done:
        raise SystemExit(f"puzzle {args.puzzle_id} is already in {UPLOADED}")
    data = next_puzzle(done) if args.upload and not args.puzzle_id else fetch_puzzle(args.puzzle_id)
    puzzle = data["puzzle"]
    out = f"puzzle_{puzzle['id']}.mp4"
    base = make_base(puzzle)
    sounds, n = [], 0  # (seconds, "move"/"capture") per landing; n counts frames written
    with tempfile.TemporaryDirectory() as tmp:
        silent = f"{tmp}/silent.mp4"
        writer = imageio_ffmpeg.write_frames(silent, (WIDTH, HEIGHT), fps=FPS, macro_block_size=1)
        writer.send(None)
        for board, seconds, tag in boards(data):
            frame = base.copy()
            frame.paste(board, BOARD_XY)
            frames = max(1, round(seconds * FPS))
            if tag in ("move", "capture"):
                sounds.append((n / FPS, tag))
            raw = frame.tobytes()
            for f in range(frames):
                writer.send(draw_timer(frame, 1 - f / frames).tobytes() if tag == "think" else raw)
            n += frames
        writer.close()
        add_sounds(silent, sounds, out)
    print(out)
    if args.upload:
        publish_at = next_publish_time(datetime.now(PUBLISH_TZ))
        video_id = upload(
            out, YT_TITLE.format(**puzzle), YT_DESCRIPTION.format(**puzzle), YT_TAGS, publish_at.isoformat()
        )
        UPLOADED.write_text(UPLOADED.read_text().rstrip("\n") + f"\n{puzzle['id']}\n")
        print(f"uploaded https://youtu.be/{video_id}, public at {publish_at:%Y-%m-%d %H:%M %Z}, recorded in {UPLOADED}")


if __name__ == "__main__":
    main()
