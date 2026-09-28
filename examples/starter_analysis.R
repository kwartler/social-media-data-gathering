# Starter analysis for a social-media-data-gathering export.
# Runs the course's three methods on one corpus:
#   1. Bag of words (tm)
#   2. Syntactic parsing (udpipe)
#   3. LLM-as-a-judge (OpenRouter, via httr2)
#
# Usage: set zip_path below (or pass it on the command line), then source the file.
#   Rscript starter_analysis.R path/to/social_media_corpus_XXXX.zip

library(tm)
library(udpipe)
library(httr2)
library(jsonlite)

args <- commandArgs(trailingOnly = TRUE)
zip_path <- if (length(args)) args[1] else file.choose()

# ---- Load ------------------------------------------------------------------
exdir <- file.path(tempdir(), "smdg_corpus")
unzip(zip_path, exdir = exdir, overwrite = TRUE)
# corpus.jsonl follows one schema (document.schema.json) for every platform,
# so this same line ingests YouTube, TikTok, Instagram, Facebook, Reddit, and Bluesky.
corpus <- stream_in(file(file.path(exdir, "corpus.jsonl"), encoding = "UTF-8"), verbose = FALSE)
cat("Documents:", nrow(corpus), "\n")
print(table(corpus$platform, corpus$doc_type))

# Choose which text to analyze. Author-written text and model-extracted text
# are different measurements (see codebook.md); combine them only on purpose.
na_blank <- function(x) ifelse(is.na(x), "", x)
corpus$analysis_text <- trimws(paste(
  na_blank(corpus$title),
  na_blank(corpus$text),
  na_blank(corpus$caption_transcript)  # add llm_transcript, on_screen_text, visual_description as needed
))
docs <- corpus[nchar(corpus$analysis_text) > 0, c("doc_id", "analysis_text")]
names(docs) <- c("doc_id", "text")

# ---- 1. Bag of words -------------------------------------------------------
clean_corpus <- function(x) {
  x <- tm_map(x, content_transformer(function(t) gsub("http\\S+|@\\S+", " ", t)))
  x <- tm_map(x, content_transformer(tolower))
  x <- tm_map(x, removePunctuation)
  x <- tm_map(x, removeNumbers)
  x <- tm_map(x, removeWords, stopwords("english"))
  tm_map(x, stripWhitespace)
}
txt_corpus <- clean_corpus(VCorpus(DataframeSource(docs)))
dtm <- DocumentTermMatrix(txt_corpus)
term_freq <- sort(colSums(as.matrix(dtm)), decreasing = TRUE)
cat("\nTop terms:\n")
print(head(term_freq, 20))

# ---- 2. Syntactic parsing --------------------------------------------------
model_dir <- tools::R_user_dir("smdg", "cache")
dir.create(model_dir, recursive = TRUE, showWarnings = FALSE)
model_file <- list.files(model_dir, pattern = "english-ewt.*\\.udpipe$", full.names = TRUE)
if (!length(model_file)) {
  model_file <- udpipe_download_model("english-ewt", model_dir = model_dir)$file_model
}
ud_model <- udpipe_load_model(model_file[1])
to_parse <- head(docs, 50)
to_parse$text <- gsub("http\\S+", " ", to_parse$text)
parsed <- as.data.frame(udpipe(to_parse, object = ud_model))
cat("\nParts of speech:\n")
print(sort(table(parsed$upos), decreasing = TRUE))
cat("\nMost common adjective + noun pairs:\n")
pairs <- merge(
  parsed[parsed$upos == "ADJ" & parsed$dep_rel == "amod", c("doc_id", "sentence_id", "head_token_id", "lemma")],
  parsed[, c("doc_id", "sentence_id", "token_id", "lemma")],
  by.x = c("doc_id", "sentence_id", "head_token_id"),
  by.y = c("doc_id", "sentence_id", "token_id"),
  suffixes = c("_adj", "_noun")
)
print(head(sort(table(paste(pairs$lemma_adj, pairs$lemma_noun)), decreasing = TRUE), 15))

# ---- 3. LLM-as-a-judge -----------------------------------------------------
# A judge labels each document against a written rubric. Always validate the
# judge against a hand-labeled sample before trusting its labels.
judge <- function(text, model = "google/gemini-3.8-flash") {
  rubric <- paste(
    "Classify the social media text below.",
    "label: one of 'opinion', 'information', 'question', 'other'.",
    "confidence: a number from 0 to 1.",
    "rationale: one short sentence citing words from the text.",
    "Reply with JSON only."
  )
  resp <- request("https://openrouter.ai/api/v1/chat/completions") |>
    req_auth_bearer_token(Sys.getenv("OPENROUTER_API_KEY")) |>
    req_body_json(list(
      model = model,
      temperature = 0,
      response_format = list(type = "json_object"),
      messages = list(
        list(role = "system", content = rubric),
        list(role = "user", content = substr(text, 1, 4000))
      )
    )) |>
    req_retry(max_tries = 3) |>
    req_perform() |>
    resp_body_json()
  out <- resp$choices[[1]]$message$content
  out <- gsub("^```(json)?\\s*|\\s*```$", "", out)
  as.data.frame(fromJSON(out))
}

if (nzchar(Sys.getenv("OPENROUTER_API_KEY"))) {
  sample_docs <- head(docs, 5)
  judged <- do.call(rbind, lapply(sample_docs$text, judge))
  cat("\nLLM-as-a-judge labels (first 5 documents):\n")
  print(cbind(doc_id = sample_docs$doc_id, judged))
} else {
  cat("\nSet OPENROUTER_API_KEY to run the LLM-as-a-judge step, for example:\n",
      "  Sys.setenv(OPENROUTER_API_KEY = \"sk-or-...\")\n")
}
