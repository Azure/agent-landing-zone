type roleAssignmentInfo = {
  @description('Role definition ID for the RBAC role to assign to the identity.')
  roleDefinitionId: string
  @description('Principal ID of the identity to assign to.')
  principalId: string
  @description('Resource ID to assing too.')
  resourceId: string
  @description('Type of principal to assign the role to.')
  principalType: 'Device' | 'ForeignGroup' | 'Group' | 'ServicePrincipal' | 'User'
}


param name string = ''

@description('Role assignments to create.')
param roleAssignments roleAssignmentInfo[] = []

module roleAssignment './resource-role-assignment.json' = [for (assignment, i) in roleAssignments: {
  // Resource IDs are module inputs, so scope is known before each deployment.
  // Empty IDs retain the caller's RG-scoped grants and their original GUIDs.
  scope: resourceGroup(
    empty(assignment.resourceId) ? subscription().subscriptionId : split(assignment.resourceId, '/')[2],
    empty(assignment.resourceId) ? resourceGroup().name : split(assignment.resourceId, '/')[4]
  )
  name: 'role-${take(name, 31)}-${uniqueString(name)}-${i}'
  params: {
    roleAssignments: [assignment]
  }
}]
