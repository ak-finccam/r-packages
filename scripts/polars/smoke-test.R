stopifnot(as.character(utils::packageVersion("polars")) == "1.15.0")

source <- data.frame(
  ISIN = c("bond-a", "bond-b", "bond-c"),
  price = c(99.5, NA_real_, 101.25),
  date = as.Date(c("2026-09-01", "2026-09-02", "2026-09-03"))
)
path <- tempfile(fileext = ".parquet")
polars::as_polars_df(source)$write_parquet(path)
result <- as.data.frame(polars::pl$scan_parquet(path)$collect())
stopifnot(isTRUE(all.equal(result, source, tolerance = 0)))
filtered <- as.data.frame(
  polars::pl$scan_parquet(path)$
    select("ISIN", "price")$
    filter(polars::pl$col("ISIN") == "bond-c")$
    collect()
)
stopifnot(identical(filtered$ISIN, "bond-c"), identical(filtered$price, 101.25))
unlink(path)
cat("Polars", as.character(utils::packageVersion("polars")), "passed: Parquet write/read, nulls, dates, projection and filtering\n")
