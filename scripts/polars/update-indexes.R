sourceArchives <- list.files("src/contrib", pattern = "\\.tar\\.gz$", full.names = TRUE)
sourceArchives <- sourceArchives[!grepl("_R_", basename(sourceArchives), fixed = TRUE)]
sourceIndex <- tempfile()
dir.create(sourceIndex)
stopifnot(all(file.copy(sourceArchives, sourceIndex)))
tools::write_PACKAGES(sourceIndex, type = "source", latestOnly = FALSE, addFiles = TRUE)
stopifnot(all(file.copy(file.path(sourceIndex, c("PACKAGES", "PACKAGES.gz", "PACKAGES.rds")), "src/contrib", overwrite = TRUE)))

tools::write_PACKAGES("bin/windows/contrib/4.5", type = "win.binary", latestOnly = FALSE, addFiles = TRUE)
tools::write_PACKAGES("bin/linux/noble/4.5/src/contrib", type = "source", latestOnly = FALSE, addFiles = TRUE, fields = "Built")
