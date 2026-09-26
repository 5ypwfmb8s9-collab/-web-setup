"""Diagramme (Altair / Vega-Lite) im KANO-Stil: dunkel, ruhig, Linien im Spectrum-Gradient."""

from __future__ import annotations

import altair as alt
import pandas as pd

BLUE, VIOLET, PINK, ORANGE, TEAL = "#2870EA", "#7B61FF", "#E3008C", "#FF8C00", "#00B7C3"
MUTED, GRID = "#8a8a8a", "#1a1a1a"
FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
# Deutsche Zahlen an Achsen: 1.500 statt 1,500 bzw. 76,5 statt 76.5
DE_INT = "replace(format(datum.value, ',.0f'), ',', '.')"
DE_DEC = "replace(format(datum.value, '.1f'), '.', ',')"

LINE_GRADIENT = alt.Gradient(
    gradient="linear",
    stops=[
        alt.GradientStop(color=BLUE, offset=0),
        alt.GradientStop(color=VIOLET, offset=0.35),
        alt.GradientStop(color=PINK, offset=0.7),
        alt.GradientStop(color=ORANGE, offset=1),
    ],
    x1=0, x2=1, y1=0, y2=0,
)
AREA_GRADIENT = alt.Gradient(
    gradient="linear",
    stops=[alt.GradientStop(color="rgba(123,97,255,0.28)", offset=0), alt.GradientStop(color="rgba(123,97,255,0)", offset=1)],
    x1=0, x2=0, y1=0, y2=1,
)


def _style(chart: alt.Chart, height: int = 220) -> alt.Chart:
    return (
        chart.properties(height=height, background="transparent")
        .configure_view(strokeWidth=0)
        .configure_axis(
            labelColor=MUTED, titleColor=MUTED, gridColor=GRID, domain=False, tickColor=GRID,
            labelFont=FONT, titleFont=FONT, labelFontSize=11, titleFontWeight=500,
        )
        .configure_legend(labelColor=MUTED, titleColor=MUTED, orient="bottom", labelFont=FONT)
    )


def weight_chart(df: pd.DataFrame, show_numbers: bool = True) -> alt.Chart:
    """df: Spalten date, weight, trend. Punkte = Tageswerte, Linie = Trend."""
    lo = min(df["weight"].min(), df["trend"].min()) - 0.8
    hi = max(df["weight"].max(), df["trend"].max()) + 0.8
    y_axis = alt.Axis(title=None, labelExpr=DE_DEC, tickCount=5) if show_numbers else alt.Axis(title=None, labels=False, ticks=False)
    x = alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m.", labelAngle=0, tickCount=5))
    scale = alt.Scale(domain=[lo, hi], zero=False)
    area = alt.Chart(df).mark_area(color=AREA_GRADIENT, interpolate="monotone").encode(
        x=x, y=alt.Y("trend:Q", scale=scale, axis=y_axis), y2=alt.datum(lo)
    )
    points = alt.Chart(df).mark_circle(size=26, color="#5a5a5a", opacity=0.9).encode(
        x=x,
        y=alt.Y("weight:Q", scale=scale),
        tooltip=[alt.Tooltip("date:T", title="Datum", format="%d.%m.%Y")]
        + ([alt.Tooltip("weight:Q", title="Gewicht", format=".1f"), alt.Tooltip("trend:Q", title="Trend", format=".1f")] if show_numbers else []),
    )
    line = alt.Chart(df).mark_line(color=LINE_GRADIENT, strokeWidth=3, interpolate="monotone").encode(
        x=x, y=alt.Y("trend:Q", scale=scale)
    )
    return _style(area + points + line)


def intake_chart(df: pd.DataFrame) -> alt.Chart:
    """df: Spalten tag (Text), gegessen, ziel. Neutral: kein Rot bei Überschreitung."""
    base = alt.Chart(df).encode(x=alt.X("tag:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)))
    bars = base.mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color=alt.Gradient(
        gradient="linear",
        stops=[alt.GradientStop(color=PINK, offset=0), alt.GradientStop(color=VIOLET, offset=0.5), alt.GradientStop(color=BLUE, offset=1)],
        x1=0, x2=0, y1=0, y2=1,
    ), size=22).encode(
        y=alt.Y("gegessen:Q", title=None, axis=alt.Axis(tickCount=4, labelExpr=DE_INT)),
        tooltip=[alt.Tooltip("tag:N", title="Tag"), alt.Tooltip("gegessen:Q", title="gegessen", format=",.0f"), alt.Tooltip("ziel:Q", title="Ziel", format=",.0f")],
    )
    target = base.mark_tick(color="#d0d0d0", thickness=2, size=30, opacity=0.8).encode(y="ziel:Q")
    return _style(bars + target, height=200)


def lines_chart(df: pd.DataFrame, y_title: str | None = None, height: int = 200, domain: list | None = None) -> alt.Chart:
    """df im Langformat: date, serie, wert."""
    colors = [BLUE, PINK, ORANGE, TEAL, VIOLET]
    series = list(dict.fromkeys(df["serie"]))
    chart = alt.Chart(df).mark_line(strokeWidth=2.5, interpolate="monotone", point=alt.OverlayMarkDef(size=28)).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%d.%m.", labelAngle=0, tickCount=5)),
        y=alt.Y("wert:Q", title=y_title, axis=alt.Axis(labelExpr=DE_INT, tickCount=5),
                scale=alt.Scale(zero=False, domain=domain) if domain else alt.Scale(zero=False)),
        color=alt.Color("serie:N", title=None, scale=alt.Scale(domain=series, range=colors[: len(series)])),
        tooltip=[alt.Tooltip("date:T", title="Datum", format="%d.%m.%Y"), alt.Tooltip("serie:N", title=""), alt.Tooltip("wert:Q", title="Wert", format=".1f")],
    )
    return _style(chart, height=height)
