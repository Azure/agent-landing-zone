# Maintenance Configuration Portal wrapper

`avm.res.maintenance.maintenance-configuration.bicep` is the release source for
the generated Maintenance Configuration wrapper consumed by
`Azure/AI-Landing-Zones`.

After publishing a release of this repository:

1. Open a companion issue in `Azure/AI-Landing-Zones`.
2. Update its Portal release reference.
3. Regenerate
   `portal/wrappers/avm.res.maintenance.maintenance-configuration.json` from this
   source.
4. Validate both jump and build VM assignments with
   `maintenanceScope: 'InGuestPatch'` on a non-isolated VM SKU.

The downstream generated JSON is not edited in this repository.
