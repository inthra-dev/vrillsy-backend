safe_run() {
  echo -e "\n[CMD] $*\n"
  "$@"
  code=$?
  if [ $code -ne 0 ]; then
    echo "❌ ERROR: command failed (exit $code)"
  fi
  return $code
}
