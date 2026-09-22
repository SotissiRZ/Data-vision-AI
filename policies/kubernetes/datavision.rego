package main

# DataVision v2.63 deployment policy. Evaluated against rendered Kubernetes YAML.

deny[msg] {
  input.kind == "Deployment"
  c := input.spec.template.spec.containers[_]
  endswith(c.image, ":latest")
  msg := sprintf("%s/%s uses a mutable latest image", [input.kind, input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  c := input.spec.template.spec.containers[_]
  not c.resources.limits
  msg := sprintf("%s/%s container %s has no resource limits", [input.kind, input.metadata.name, c.name])
}

deny[msg] {
  input.kind == "Deployment"
  c := input.spec.template.spec.containers[_]
  not c.resources.requests
  msg := sprintf("%s/%s container %s has no resource requests", [input.kind, input.metadata.name, c.name])
}

deny[msg] {
  input.kind == "Secret"
  some k
  v := input.stringData[k]
  contains(upper(sprintf("%v", [v])), "CHANGE_ME")
  msg := sprintf("Secret/%s contains placeholder value in key %s", [input.metadata.name, k])
}

deny[msg] {
  input.kind == "Service"
  input.spec.type == "LoadBalancer"
  not input.metadata.annotations["datavision.ai/public-service-approved"] == "true"
  msg := sprintf("Service/%s exposes LoadBalancer without explicit approval annotation", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  input.metadata.name != ""
  c := input.spec.template.spec.containers[_]
  c.imagePullPolicy == "Always"
  endswith(c.image, ":latest")
  msg := sprintf("Deployment/%s combines Always pull policy with latest tag", [input.metadata.name])
}

# v2.64 runtime hardening controls.
deny[msg] {
  input.kind == "Deployment"
  not input.spec.template.spec.securityContext.runAsNonRoot == true
  msg := sprintf("Deployment/%s must set pod runAsNonRoot=true", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  not input.spec.template.spec.securityContext.seccompProfile.type == "RuntimeDefault"
  msg := sprintf("Deployment/%s must use seccomp RuntimeDefault", [input.metadata.name])
}

deny[msg] {
  input.kind == "Deployment"
  c := input.spec.template.spec.containers[_]
  not c.securityContext.allowPrivilegeEscalation == false
  msg := sprintf("Deployment/%s container %s allows privilege escalation", [input.metadata.name, c.name])
}

drops_all_capabilities(c) {
  some i
  c.securityContext.capabilities.drop[i] == "ALL"
}

deny[msg] {
  input.kind == "Deployment"
  c := input.spec.template.spec.containers[_]
  not drops_all_capabilities(c)
  msg := sprintf("Deployment/%s container %s must drop ALL capabilities", [input.metadata.name, c.name])
}
