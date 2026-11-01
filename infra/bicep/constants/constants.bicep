//https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations
@export()
var abbrs = loadJsonContent('../../shared/abbreviations.json')

@export()
var roles = loadJsonContent('../../shared/roles.json')

@export()
@description('Information about a workload profile for the environment.')
type workloadProfileInfo = {
  @description('Friendly name of the workload profile.')
  name: string
  @description('Type of the workload profile.')
  workloadProfileType:
    | 'Consumption'
    | 'D4'
    | 'D8'
    | 'D16'
    | 'D32'
    | 'E4'
    | 'E8'
    | 'E16'
    | 'E32'
    | 'NC24-A100'
    | 'NC48-A100'
    | 'NC96-A100'
  @description('Minimum number of nodes for the workload profile.')
  minimumCount: int!
  @description('Maximum number of nodes for the workload profile.')
  maximumCount: int!
}
