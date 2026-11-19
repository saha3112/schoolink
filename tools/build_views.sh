#!/bin/zsh
# Re-generate app/views_py/*.py from the original PHP report templates.
# usage: tools/build_views.sh /path/to/old/application/views
V=${1:-/usr/local/var/www/schoollink-report-card/application/views}
cd "$(dirname "$0")/.."
for f in $V/reportCard/*.php $V/tabulation/sheet.php $V/tabulation/junior_sheet.php $V/tabulation/weighted_sheet.php $V/tabulation/junior_weighted_sheet.php; do
  b=$(basename $f .php | tr 'A-Z' 'a-z')
  .venv/bin/python tools/php2py.py $f app/views_py/$b.py >/dev/null || echo "FAILED $f"
done
