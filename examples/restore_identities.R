# Restore real names and links to a pseudonymized export.
#
# This script does one thing: it swaps the pseudonyms (u_3f9a1c02de) back to the
# real account names, @mentions, and post links, using the key the app saved in
# the export's identifiable/ folder.
#
# HOW TO RUN (no programming needed)
#   1. Open this file in RStudio (File > Open File...).
#   2. Click the "Source" button at the top right of this file.
#   3. A window opens: choose the .zip file the app gave you.
#   4. Your file appears in a new folder next to the zip, named "..._identified":
#        corpus_identified.csv   every post and comment with real names and links
#
# KEEP THIS FILE PRIVATE. It contains real names. Store it where your IRB
# protocol says, never share it with classmates, and delete it on schedule.
#
# Needs one package: install.packages("jsonlite")

library(jsonlite)

# ---- 1. Open the export -----------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
zip_path <- if (length(args)) args[1] else file.choose()

out_dir <- file.path(dirname(zip_path), paste0(tools::file_path_sans_ext(basename(zip_path)), "_identified"))
dir.create(out_dir, showWarnings = FALSE)
unzip_dir <- file.path(tempdir(), "smdg_restore")
unlink(unzip_dir, recursive = TRUE)
unzip(zip_path, exdir = unzip_dir)

key_file <- file.path(unzip_dir, "identifiable", "linking_key.csv")
names_file <- file.path(unzip_dir, "identifiable", "pseudonym_key.csv")
if (!file.exists(key_file)) {
  stop("This export has no identifiable/linking_key.csv, so there is nothing to restore. ",
       "Either it was collected with Pseudonymize set to 'No one' (names are already real), ",
       "or 'Include identifiable folder' was turned off.", call. = FALSE)
}

corpus <- stream_in(file(file.path(unzip_dir, "corpus.jsonl"), encoding = "UTF-8"), verbose = FALSE)
key <- read.csv(key_file, encoding = "UTF-8", stringsAsFactors = FALSE, na.strings = character(0))
pseudonyms <- read.csv(names_file, encoding = "UTF-8", stringsAsFactors = FALSE, na.strings = character(0))

# ---- 2. Put real authors and links back -------------------------------------
m <- match(corpus$doc_id, key$doc_id)
has_key <- !is.na(m)
corpus$author[has_key] <- key$author[m[has_key]]
corpus$author_id[has_key] <- key$author_id[m[has_key]]
corpus$url[has_key] <- key$url[m[has_key]]

# ---- 3. Put real @mentions back inside the text -----------------------------
lookup <- setNames(pseudonyms$original, pseudonyms$pseudonym)
no_at <- !startsWith(lookup, "@")
lookup[no_at] <- paste0("@", lookup[no_at])  # ifelse() would drop the names, so assign in place

restore_mentions <- function(x) {
  hits <- gregexpr("@u_[0-9a-f]{10}", x)
  regmatches(x, hits) <- lapply(regmatches(x, hits), function(tokens) {
    original <- lookup[substring(tokens, 2)]
    ifelse(is.na(original), tokens, original)
  })
  x
}

text_fields <- c("title", "text", "caption_transcript", "llm_transcript", "on_screen_text", "alt_text",
                 "translated_title", "translated_text", "translated_caption_transcript",
                 "translated_llm_transcript", "translated_on_screen_text")
for (f in intersect(text_fields, names(corpus))) {
  corpus[[f]] <- restore_mentions(corpus[[f]])
}

# ---- 4. Save for spreadsheets -----------------------------------------------
speakers_text <- function(s) {
  if (is.null(s) || !length(s) || !nrow(as.data.frame(s))) return("")
  s <- as.data.frame(s)
  paste0(s$id, ": ", s$description, ifelse(s$on_screen, " (on screen)", ""), collapse = " | ")
}
corpus$speakers <- vapply(corpus$speakers, speakers_text, character(1))
corpus$segments <- NULL  # time-stamped segments stay in segments.csv

out_file <- file.path(out_dir, "corpus_identified.csv")
bom <- file(out_file, open = "wb")
writeBin(as.raw(c(0xEF, 0xBB, 0xBF)), bom)  # byte order mark so Excel shows emoji and accents correctly
close(bom)
con <- file(out_file, open = "a", encoding = "UTF-8")
write.csv(corpus, con, row.names = FALSE, na = "")
close(con)

cat("\nRestored", sum(has_key), "of", nrow(corpus), "documents and",
    nrow(pseudonyms), "pseudonyms.\nSaved:", out_file,
    "\nThis file contains real names: keep it private.\n")
