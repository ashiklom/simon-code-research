terraform {
  required_version = ">= 1.10"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.73" }
    archive = { source = "hashicorp/archive", version = "~> 2.8" }
    random  = { source = "hashicorp/random", version = "~> 3.9" }
    http    = { source = "hashicorp/http", version = "~> 3.6" }
  }
}
