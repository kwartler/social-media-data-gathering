# Build a review sheet for checking the model's work by hand, then score it.
#
# Model output (transcripts, speaker labels, on-screen text, visual descriptions,
# translations) is unverified. This script picks a random sample of posts and
# makes a spreadsheet with empty columns where you record whether the model got
# each part right. Report the results in your methods section.
#
# HOW TO RUN (no programming needed)
#   1. Open this file in RStudio and click "Source".
#   2. A window opens: choose ONE of these files:
#        - corpus_identified.csv from restore_identities.R (if your export was pseudonymized), or
#        - the .zip from the app (if Pseudonymize was set to "No one")
#      The sheet needs real links so you can open each post.
#   3. review_sheet.csv appears in the same folder. Open it in Excel.
#   4. For each row, open the url, watch the post, and fill in each check_ column:
#        yes = correct   partly = small errors   no = wrong   na = does not apply
#   5. Save it, then in the RStudio console run:
#        summarize_review("path/to/review_sheet.csv")
#
# If the sheet contains real names, keep it private.
#
# Needs one package: install.packages("jsonlite")

library(jsonlite)

# ---- Settings you can change ------------------------------------------------
review_sample_size <- 20   # posts to review (all of them if there are fewer)
random_seed <- 1           # change for a different random sample

# ---- Scoring (run after you fill in the sheet) --------------------------------
# Counts yes / partly / no for each check column, so you can report, for example,
# "the model's transcripts were fully correct for 17 of 20 sampled posts".
summarize_review <- function(path) {
  r <- read.csv(path, encoding = "UTF-8", stringsAsFactors = FALSE, check.names = FALSE)
  names(r) <- sub("^﻿", "", names(r))
  checks <- grep("^check_", names(r), value = TRUE)
  out <- t(sapply(checks, function(col) {
    v <- tolower(trimws(r[[col]]))
    v[is.na(v)] <- ""
    c(yes = sum(v == "yes"), partly = sum(v == "partly"), no = sum(v == "no"),
      na = sum(v == "na"), blank = sum(v == ""))
  }))
  print(out)
  invisible(out)
}

# ---- 1. Load the corpus -----------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
in_path <- if (length(args)) args[1] else file.choose()

if (grepl("\\.zip$", in_path, ignore.case = TRUE)) {
  unzip_dir <- file.path(tempdir(), "smdg_review")
  unlink(unzip_dir, recursive = TRUE)
  unzip(in_path, exdir = unzip_dir)
  corpus <- stream_in(file(file.path(unzip_dir, "corpus.jsonl"), encoding = "UTF-8"), verbose = FALSE)
  corpus$speakers <- vapply(corpus$speakers, function(s) {
    s <- as.data.frame(s)
    if (!nrow(s)) return("")
    paste0(s$id, ": ", s$description, ifelse(s$on_screen, " (on screen)", ""), collapse = " | ")
  }, character(1))
  if (all(corpus$url == "")) {
    warning("This export is pseudonymized, so the sheet has no links. ",
            "Run restore_identities.R first and choose corpus_identified.csv instead.", call. = FALSE)
  }
} else {
  corpus <- read.csv(in_path, encoding = "UTF-8", stringsAsFactors = FALSE, check.names = FALSE,
                     na.strings = character(0))
  names(corpus) <- sub("^﻿", "", names(corpus))
  corpus$ai_generated <- toupper(as.character(corpus$ai_generated)) == "TRUE"
}

# ---- 2. Sample posts with model output ----------------------------------------
to_review <- corpus[corpus$doc_type == "post" & corpus$ai_generated, ]
if (!nrow(to_review)) stop("No posts with model output to review.", call. = FALSE)
set.seed(random_seed)
if (nrow(to_review) > review_sample_size) {
  to_review <- to_review[sample(nrow(to_review), review_sample_size), ]
}

review_cols <- c("doc_id", "platform", "url", "author", "title", "text",
                 "caption_transcript", "llm_transcript", "speakers", "on_screen_text",
                 "visual_description", "translation_language", "translated_llm_transcript")
review <- to_review[, intersect(review_cols, names(to_review)), drop = FALSE]
review$check_transcript <- ""
review$check_speakers <- ""
review$check_on_screen_text <- ""
review$check_visual_description <- ""
review$check_translation <- ""
review$reviewer_notes <- ""

# ---- 3. Save ------------------------------------------------------------------
out_file <- file.path(dirname(in_path), "review_sheet.csv")
bom <- file(out_file, open = "wb")
writeBin(as.raw(c(0xEF, 0xBB, 0xBF)), bom)  # byte order mark so Excel shows emoji and accents correctly
close(bom)
con <- file(out_file, open = "a", encoding = "UTF-8")
write.csv(review, con, row.names = FALSE, na = "")
close(con)

cat("\nReview sheet with ", nrow(review), " posts saved to: ", out_file,
    "\nFill in the check_ columns, then run summarize_review(\"", out_file, "\")\n", sep = "")
