---
title: "Entity Framework Core 11 provider for Firebird is ready"
date: 2026-11-24
summary: "FirebirdSql.EntityFrameworkCore.Firebird 14.0 supports Entity Framework Core 11."
---
The Firebird .NET team has released version **14.0** of the **FirebirdSql.EntityFrameworkCore.Firebird** package.
This is the Firebird provider for **Entity Framework Core 11**.
Note: 14.0 is the version of the provider package, and EF Core 11 is the version of the framework that it supports.

The provider lets .NET applications work with Firebird databases through EF Core: LINQ queries, migrations, and model building.

Download it from [NuGet](https://www.nuget.org/packages/FirebirdSql.EntityFrameworkCore.Firebird).
The source code is on [GitHub](https://github.com/FirebirdSQL/NETProvider).

## What's new

- **Entity Framework Core 11 support** ([#1280](https://github.com/FirebirdSQL/NETProvider/issues/1280)).
- **Stored procedure mapping:** you can now use `InsertUsingStoredProcedure`, `UpdateUsingStoredProcedure` and `DeleteUsingStoredProcedure` in the model builder ([#1158](https://github.com/FirebirdSQL/NETProvider/issues/1158), [PR #1185](https://github.com/FirebirdSQL/NETProvider/pull/1185)).
- **Fix:** correlated queryable (table-valued) functions now work. The function is now wrapped in a derived table after `LATERAL` ([#1277](https://github.com/FirebirdSQL/NETProvider/issues/1277)).
- **Fix:** expression indexes are now excluded at the database level when the provider reads indexes during scaffolding ([#1188](https://github.com/FirebirdSQL/NETProvider/issues/1188), [PR #1262](https://github.com/FirebirdSQL/NETProvider/pull/1262)).
- **Fix:** the `Value` column is now quoted correctly in `Single`/`SingleOrDefault` queries, and new tests cover it ([#1234](https://github.com/FirebirdSQL/NETProvider/issues/1234), [PR #1263](https://github.com/FirebirdSQL/NETProvider/pull/1263)).

See the [full list of changes in the EFCore-14.0.0.0 milestone](https://github.com/FirebirdSQL/NETProvider/milestone/108?closed=1).
