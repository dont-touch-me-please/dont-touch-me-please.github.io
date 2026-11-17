"""
Сборка данных статической версии сервиса.

Читает выгрузки ГКО теми же модулями, что и основной проект
(valuation.table_reader), и раскладывает результат по кадастровым
районам: один файл JSON на район. Запись об участке:

    [номер, КС нового тура (коп.), КС действующего тура (коп.),
     площадь (кв.м x 100), оценочный сегмент, группа ставки]

Группа ставки определяется так же, как в views._rate_for основного
проекта: по виду использования и категории земель, если они есть в
выгрузке, иначе по оценочному сегменту.

Запуск:
    python build_static.py КАТАЛОГ_2019 КАТАЛОГ_2022 КАТАЛОГ_САЙТА
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent.parent / "gko"
sys.path.insert(0, str(PROJECT))
from valuation.table_reader import read_rows  # noqa: E402
from valuation.taxes import rate_group_for, rate_group_for_segment  # noqa: E402

SEG_RE = re.compile(r"(?<!\d)(\d{1,2})\s*сегмент", re.IGNORECASE)
GROUPS = ["residential", "garden", "agricultural", "preferential", "general"]
UNKNOWN_GROUP = 5  # вид использования не указан и сегмент неизвестен


def kop(value) -> int:
    return int((value * 100).to_integral_value())


def collect(directory: Path, label: str) -> dict:
    out = {}
    files = sorted(p for p in directory.rglob("*")
                   if p.suffix.lower() in (".xlsx", ".ods")
                   and "ОНС" not in p.name and "Сведения" not in p.name)
    for path in files:
        m = SEG_RE.search(path.name)
        seg = int(m.group(1)) if m else None
        rows, stats = read_rows(path, land_only=True, default_segment=seg)
        n = 0
        for r in rows:
            d, q, o = (int(x) for x in r.cadastral_number.split(":")[1:4])
            segment = r.segment or seg
            if r.permitted_use or r.category:
                group = GROUPS.index(rate_group_for(r.permitted_use, r.category))
            elif rate_group_for_segment(segment):
                group = GROUPS.index(rate_group_for_segment(segment))
            else:
                group = UNKNOWN_GROUP
            area = int((r.area * 100).to_integral_value()) if r.area else 0
            out[(d, q, o)] = (kop(r.cadastral_value), area, segment or 0, group)
            n += 1
        print(f"  {label} {path.name[:34]:<34} строк {n:>7} "
              f"отклонено {stats.rows_rejected:>4}", flush=True)
    print(f"{label}: участков {len(out)}", flush=True)
    return out


def rates_table(csv_path: Path) -> dict:
    """Справочник ставок: район -> {название, ставки по годам и группам}."""
    table, sources = {}, []
    with open(csv_path, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.startswith("#")]
    for row in csv.DictReader(lines, delimiter=";"):
        if row["source"] not in sources:
            sources.append(row["source"])
        for district in row["districts"].split(","):
            d = str(int(district.strip().split(":")[1]))
            entry = table.setdefault(d, {"m": row["municipality"], "r": {}})
            entry["r"].setdefault(row["year"], {})[row["group"]] = [
                row["rate"], sources.index(row["source"])]
    return {"sources": sources, "districts": table}


def main(dir_old: str, dir_new: str, site: str) -> None:
    new = collect(Path(dir_new), "2022")
    old = collect(Path(dir_old), "2019")

    by_district = defaultdict(lambda: defaultdict(list))
    for key in set(new) | set(old):
        d, q, o = key
        n, c = new.get(key), old.get(key)
        ref = c or n                      # как в views: reference = current or upcoming
        by_district[d][q].append([
            o,
            n[0] if n else 0,
            c[0] if c else 0,
            (c[1] if c and c[1] else (n[1] if n else 0)),
            (n or c)[2],
            ref[3],
        ])

    data = Path(site) / "data"
    data.mkdir(parents=True, exist_ok=True)
    total = 0
    for d, quarters in by_district.items():
        for rows in quarters.values():
            rows.sort()
        payload = json.dumps({str(q): rows for q, rows in sorted(quarters.items())},
                             separators=(",", ":"))
        (data / f"{d}.json").write_text(payload, encoding="utf-8")
        total += len(payload)

    rates = rates_table(PROJECT / "data_templates" / "rates_saratov.csv")
    (data / "rates.json").write_text(
        json.dumps(rates, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    meta = {
        "parcels": len(set(new) | set(old)),
        "both": len(set(new) & set(old)),
        "only_new": len(set(new) - set(old)),
        "only_old": len(set(old) - set(new)),
        "districts": sorted(by_district),
    }
    (data / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    print(f"\nрайонов {len(by_district)}, участков {meta['parcels']}, "
          f"данные {total / 1048576:.1f} МБ")
    print(meta["both"], meta["only_new"], meta["only_old"])


if __name__ == "__main__":
    main(*sys.argv[1:4])
