{{- define "datavision.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "datavision.fullname" -}}
{{- if .Values.fullnameOverride -}}{{ .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}{{- else -}}{{ include "datavision.name" . }}{{- end -}}
{{- end -}}
{{- define "datavision.labels" -}}
app.kubernetes.io/name: {{ include "datavision.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "datavision.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else if .Values.secrets.create -}}
{{- printf "%s-secrets" (include "datavision.fullname" .) -}}
{{- else -}}
{{- fail "secrets.existingSecret must be set when secrets.create=false" -}}
{{- end -}}
{{- end -}}
