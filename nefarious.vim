" Vim syntax file
" Language: Nefarious Scheme
" Maintainer: Tim Radvan
" Latest Revision: 9 Nov 2016

if exists("b:current_syntax")
  finish
endif

let b:current_syntax = "nefarious"

"syntax iskeyword @,48-57,192-255,:,=,_
"syntax iskeyword @,48-57,192-255,$,_

syntax keyword nfsKeyword let var fun define defprim
syntax match nfsKeyword "\v\="
syntax match nfsKeyword "\v\:\="
highlight link nfsKeyword Operator

syntax keyword nfsType Int Float Bool Text List Var Any Record
highlight link nfsType Type

syntax keyword nfsBoolean yes
syntax keyword nfsBoolean no
syntax keyword nfsBoolean nil
highlight link nfsBoolean Boolean

syntax match nfsNumber "[0-9]+"
highlight link nfsInt Number

syntax match nfsFloat "\v[0-9]+(\.[0-9]+)?(e[+-][0-9]+)?"
highlight link nfsFloat Float

syntax match nfsSymbol "\v:[a-zA-Z]+"
highlight link nfsSymbol Function

"syn region definition start='defprim ' end='{'
"syn region definition start='func' end='{'
"syn region definition start='define ' end='{'
"highlight link definition NonText

syntax match nfsBrace "\v\{"
syntax match nfsBrace "\v\}"
highlight link nfsBrace Define

syntax region nfsString start=/\v"/ skip=/\v\\./ end=/\v"/
highlight link nfsString String

syntax keyword prim FLOAT_SUB
syntax keyword prim FLOAT_ADD
syntax keyword prim FLOAT_MUL
syntax keyword prim FLOAT_DIV
syntax keyword prim BOOL_AND
syntax keyword prim BOOL_OR
syntax keyword prim BOOL_NOT
syntax keyword prim INT_ADD
syntax keyword prim INT_SUB
syntax keyword prim INT_MUL
syntax keyword prim INT_LT
syntax keyword prim INT_EQ
syntax keyword prim INT_RANDOM
syntax keyword prim INT_FLOAT
syntax keyword prim FLOAT_ADD
syntax keyword prim FLOAT_SUB
syntax keyword prim FLOAT_LT
syntax keyword prim FLOAT_ROUND
syntax keyword prim TEXT_JOIN
syntax keyword prim TEXT_JOIN_WITH
syntax keyword prim TEXT_SPLIT
syntax keyword prim TEXT_SPLIT_BY
syntax keyword prim LIST_ADD
syntax keyword prim LIST_LEN
syntax keyword prim LIST_GET
syntax keyword prim LIST_SET
syntax keyword prim IF_THEN_ELSE
syntax keyword prim IF_THEN
syntax keyword prim WHILE
syntax keyword prim PRINT
syntax keyword prim REPR
syntax keyword prim IS_NIL
highlight link prim Special
