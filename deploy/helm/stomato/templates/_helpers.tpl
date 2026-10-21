{{/* names, labels, image references shared by every template */}}

{{- define "stomato.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "stomato.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "stomato.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "stomato.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "stomato.labels" -}}
helm.sh/chart: {{ include "stomato.chart" . }}
app.kubernetes.io/name: {{ include "stomato.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "stomato.selectorLabels" -}}
app.kubernetes.io/name: {{ include "stomato.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "stomato.componentLabels" -}}
{{- $component := .component -}}
{{- with .context -}}
{{ include "stomato.labels" . }}
app.kubernetes.io/component: {{ $component }}
{{- end -}}
{{- end -}}

{{- define "stomato.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion -}}
{{- end -}}
