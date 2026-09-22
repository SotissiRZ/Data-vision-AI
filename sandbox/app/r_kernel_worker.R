suppressWarnings(suppressMessages(library(jsonlite)))
input <- file("stdin", open="r")
execution_count <- 0

truncate_text <- function(value, max_chars=120000) {
  value <- paste(value, collapse="\n")
  if (nchar(value) <= max_chars) value else paste0(substr(value, 1, max_chars), "\n… sortie tronquée par DataVision …")
}

serialize_value <- function(value) {
  if (is.null(value)) return(list(type="none", value=NULL))
  if (is.data.frame(value)) {
    preview <- head(value, 200)
    return(list(
      type="dataframe",
      columns=names(preview),
      rows=unname(split(preview, seq_len(nrow(preview)))),
      shape=list(nrow(value), ncol(value)),
      truncated=nrow(value) > 200
    ))
  }
  if (is.atomic(value) && length(value) <= 2000) {
    return(list(type=class(value)[1], value=value))
  }
  list(type=class(value)[1], value=substr(paste(capture.output(str(value)), collapse="\n"), 1, 5000))
}

repeat {
  line <- readLines(input, n=1, warn=FALSE)
  if (length(line) == 0) break
  request <- tryCatch(fromJSON(line, simplifyVector=FALSE), error=function(e) NULL)
  if (is.null(request)) {
    cat(toJSON(list(status="failed", error_type="ProtocolError"), auto_unbox=TRUE), "\n", sep="")
    flush.console()
    next
  }
  action <- ifelse(is.null(request$action), "execute", request$action)
  if (action == "shutdown") {
    cat(toJSON(list(status="ok", execution_count=execution_count), auto_unbox=TRUE), "\n", sep="")
    flush.console()
    break
  }
  if (action == "inspect") {
    vars <- setdiff(ls(envir=.GlobalEnv), c("data", "dataset", "dv_save_dataframe", "dv_save_json"))
    cat(toJSON(list(status="ok", execution_count=execution_count, variables=head(vars, 200)), auto_unbox=TRUE), "\n", sep="")
    flush.console()
    next
  }

  dataset_path <- request$dataset_path
  output_dir <- request$output_dir
  dir.create(output_dir, recursive=TRUE, showWarnings=FALSE)
  data <- read.csv(dataset_path, check.names=FALSE)
  dataset <- data
  assign("data", data, envir=.GlobalEnv)
  assign("dataset", dataset, envir=.GlobalEnv)
  assign("OUTPUT_DIR", output_dir, envir=.GlobalEnv)

  dv_save_dataframe <- function(frame, name="result.csv") {
    target <- file.path(output_dir, basename(name))
    write.csv(frame, target, row.names=FALSE)
    target
  }
  dv_save_json <- function(value, name="result.json") {
    target <- file.path(output_dir, basename(name))
    write(toJSON(value, auto_unbox=TRUE, dataframe="rows", null="null"), file=target)
    target
  }
  assign("dv_save_dataframe", dv_save_dataframe, envir=.GlobalEnv)
  assign("dv_save_json", dv_save_json, envir=.GlobalEnv)

  output <- character()
  messages <- character()
  result <- NULL
  error_type <- NULL
  status <- "succeeded"
  tryCatch({
    output <- capture.output({
      exprs <- parse(text=ifelse(is.null(request$code), "", request$code))
      if (length(exprs) > 0) {
        for (expr in exprs) result <- eval(expr, envir=.GlobalEnv)
      }
    }, type="output")
    execution_count <- execution_count + 1
  }, error=function(e) {
    status <<- "failed"
    error_type <<- class(e)[1]
    messages <<- conditionMessage(e)
  })

  response <- list(
    status=status,
    engine="r-persistent",
    stdout=truncate_text(output),
    stderr=truncate_text(messages),
    result=if (status == "succeeded") serialize_value(result) else NULL,
    error_type=error_type,
    execution_count=execution_count
  )
  cat(toJSON(response, auto_unbox=TRUE, dataframe="rows", null="null"), "\n", sep="")
  flush.console()
}
