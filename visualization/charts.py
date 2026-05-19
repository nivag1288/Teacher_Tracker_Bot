import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

_BG = "#1c2230"
_CARD = "#0f1117"
_ACCENT = "#58a6ff"
_TEXT = "#e6edf3"
_MUTED = "#8b949e"


def _apply_dark(fig, axes):
    fig.patch.set_facecolor(_BG)
    for ax in (axes if hasattr(axes, "__iter__") else [axes]):
        ax.set_facecolor(_BG)
        ax.tick_params(colors=_MUTED, labelsize=8)
        ax.xaxis.label.set_color(_MUTED)
        ax.yaxis.label.set_color(_MUTED)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363d")


def _encode(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def hourly_heatmap(data: list[dict]) -> str:
    """Hour-of-day × weekday message heatmap.

    data: list of {"hour": int, "weekday": int, "count": int}
    Returns base64 PNG string.
    """
    matrix = np.zeros((7, 24))
    for row in data:
        matrix[int(row["weekday"]), int(row["hour"])] += row["count"]

    fig, ax = plt.subplots(figsize=(12, 3))
    _apply_dark(fig, ax)

    cmap = mcolors.LinearSegmentedColormap.from_list("blue_heat", [_BG, _ACCENT])
    im = ax.imshow(matrix, aspect="auto", cmap=cmap)

    day_labels = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    ax.set_yticks(range(7))
    ax.set_yticklabels(day_labels, color=_MUTED, fontsize=8)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)], color=_MUTED, fontsize=8)
    ax.set_xlabel("Hour (UTC)", color=_MUTED, fontsize=9)

    cb = fig.colorbar(im, ax=ax, pad=0.02)
    cb.ax.tick_params(colors=_MUTED, labelsize=8)
    cb.set_label("Messages", color=_MUTED, fontsize=8)

    return _encode(fig)


def daily_trend(data: list[dict]) -> str:
    """Messages-per-day line chart.

    data: list of {"date": str, "count": int}
    Returns base64 PNG string.
    """
    if not data:
        fig, ax = plt.subplots(figsize=(10, 3))
        _apply_dark(fig, ax)
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=_MUTED,
                transform=ax.transAxes, fontsize=11)
        ax.set_axis_off()
        return _encode(fig)

    dates = [r["date"] for r in data]
    counts = [r["count"] for r in data]
    xs = range(len(dates))

    fig, ax = plt.subplots(figsize=(10, 3))
    _apply_dark(fig, ax)

    ax.plot(xs, counts, color=_ACCENT, linewidth=1.5)
    ax.fill_between(xs, counts, alpha=0.15, color=_ACCENT)
    ax.set_ylabel("Messages", color=_MUTED, fontsize=9)

    step = max(1, len(dates) // 8)
    ax.set_xticks(list(range(0, len(dates), step)))
    ax.set_xticklabels([dates[i] for i in range(0, len(dates), step)],
                       rotation=35, ha="right", fontsize=8, color=_MUTED)

    return _encode(fig)


def user_bar(data: list[dict]) -> str:
    """Horizontal bar chart of top users by message count.

    data: list of {"author_name": str, "count": int}
    Returns base64 PNG string.
    """
    if not data:
        fig, ax = plt.subplots(figsize=(8, 2))
        _apply_dark(fig, ax)
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color=_MUTED,
                transform=ax.transAxes, fontsize=11)
        ax.set_axis_off()
        return _encode(fig)

    names = [r["author_name"] for r in data]
    counts = [r["count"] for r in data]

    fig, ax = plt.subplots(figsize=(8, max(2, len(names) * 0.45)))
    _apply_dark(fig, ax)

    bars = ax.barh(names, counts, color=_ACCENT, height=0.6)
    ax.invert_yaxis()
    ax.set_xlabel("Messages", color=_MUTED, fontsize=9)
    ax.tick_params(axis="y", labelsize=9, colors=_TEXT)

    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() + max(counts) * 0.01, bar.get_y() + bar.get_height() / 2,
                str(count), va="center", fontsize=8, color=_MUTED)

    return _encode(fig)
