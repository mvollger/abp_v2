#!/usr/bin/env python
import glob
import subprocess
import os
import sys
import re
import itertools 
import os
import pandas as pd
import numpy as np
pd.set_option('display.max_rows', 500)
pd.set_option('display.max_columns', 500)
pd.set_option('display.width', 20000000)
from Bio import SeqIO
if sys.version_info[0] < 3: 
    from StringIO import StringIO
else:
    from io import StringIO



class Aln:
	def __init__(self, best=None, ave=None, seq="NA", CC_ID="NA"):
		if(CC_ID=="NA"):
			print("ummmm")

		self.CC_ID = CC_ID
		if(seq == "NA"):
			self.name = seq
		else:
			self.name = seq.name

		if(best is None):
			self.best ="NA"
			self.ave ="NA"
			self.avePerID = 0.0
			self.bestPerID = 0.0
			self.aveAlnLen = 0.0
			self.bestAlnLen = 0.0
			self.bestRefRegion ="NA"
			self.bestChr ="chr1"
			self.bestStart = 0
			self.bestEnd = 0
		else:
			#print(best)
			self.best = best
			self.ave = ave
			self.perID()
			self.aveAlnLen = ( self.ave[3] - self.ave[2] ).mean()
			self.bestAlnLen = ( self.best[8] - self.best[7] ).mean()
			self.bestRefRegion = self.best.iloc[0][5]
			match = re.match("(.+):(\d+)-(\d+)", self.bestRefRegion)
			self.bestChr = match.group(1)
			self.bestStart = int(match.group(2)) + self.best.iloc[0][7]   
			self.bestEnd =   int(match.group(2)) + self.best.iloc[0][8] 

	def asPD(self):
		dic = vars(self).copy()
		del dic["best"]
		del dic["ave"]
		rtn = pd.Series(dic)
		rtn.fillna(0,  inplace=True)
		#pd.concat([s1,s2]).to_frame().T
		return(rtn)

	def perID(self):
		bestPerID = self.best[11]/(self.best[11] + self.best[12])
		avePerID = self.ave[11]/(self.ave[11] + self.ave[12])
		self.bestPerID = bestPerID.mean()
		self.avePerID = avePerID.mean()

class Asm:
	def __init__(self, asmPath, m5Paths, CC_ID):
		self.CC_ID = CC_ID
		self.contigs = []
		self.num = 0
		self.m5Paths = m5Paths
		self.asmPath = asmPath 
		self.readIn()
		self.getAln()
		self.pd = None
		if(len(self.contigs) > 0):
			self.pd = pd.concat(self.contigs, axis = 1,ignore_index=True).T 
	
	def readIn(self):
		self.seqs = []
		if( os.path.exists(self.asmPath) ):
			self.seqs = list(SeqIO.parse(self.asmPath, "fasta"))
			self.num = len(self.seqs)
		if(os.path.exists(self.m5Paths["best"]) and os.path.exists(self.m5Paths["average"])):
			if( (os.stat(self.m5Paths["best"]).st_size != 0) and 
					(os.stat(self.m5Paths["average"]).st_size != 0)):
				self.best = pd.read_table(self.m5Paths["best"], sep=" ", header=None)
				self.ave = pd.read_table(self.m5Paths["average"], sep=" ", header=None)
				# 0 read name
				# 1 length 
				# 2-3 start end
				# 5 ref name 

	def getAln(self):
		if(len(self.seqs) == 0):
			self.contigs.append( Aln(CC_ID = self.CC_ID).asPD() )
		for seq in self.seqs:
			name = seq.name.strip()
			#print(name)
			#print(self.best)
			#print(self.best[0].str.contains(name,  regex=False))
			#print(self.best.loc[ self.best[0].str.contains(name,  regex=False) ])
			#print("\n")
			bestaln = self.best.loc[ self.best[0].str.contains(name,  regex=False) ]
			avealn = self.ave.loc[self.ave[5].str.contains(name, regex=False) ]
			if(bestaln.empty and avealn.empty):
				self.contigs.append( Aln( seq=seq, CC_ID=self.CC_ID ).asPD() )
			else:
				self.contigs.append(Aln(bestaln, avealn, seq, self.CC_ID).asPD())
		

class LocalAssembly:	
	def __init__(self, mydir, psvGraphLoc=None, psvURLPATH=None):
		self.mydir = os.path.abspath(mydir.strip()) + "/"
		self.determineGroups()
		# this means there were zero groups generated by CC
		if(len(self.ids) == 0):
			return 
		self.findAsm()
		self.fillInFailed()
		self.addStatus()
		self.addPSVs()
		self.addReads()
		self.addCommon()
		self.truthMatrix()
		#print(self.all.to_string(index=False))
		self.toFile()
	
	def addReads(self):
		self.numReads = []
		for idx in self.ids:
			sam = "{}group.{}/H2.WH.sam".format(self.mydir, idx)
			reads = 0
			if(os.path.exists(sam)):
				f = open(sam)
				for line in f:
					line = line.strip()
					if(line[0] not in ["@", "\n", "\t", " "] ):
						reads += 1
			self.numReads.append(reads)

		temp = pd.DataFrame({"numReads":self.numReads, "CC_ID":self.ids})
		self.all = pd.merge( self.all, temp, how='left', on ="CC_ID")
		
		sam = self.mydir + "reads.fasta"
		reads = 0
		if(os.path.exists(sam)):
			f = open(sam)
			for line in f:
				line = line.strip()
				if(line[0] == ">" ):
					reads += 1
		self.totalReads = reads
		self.all["totalReads"] = reads 

	def toFile(self):
		fname = self.mydir + self.collapse + ".table.tsv"
		fname = self.mydir + "abp.table.tsv"
		subset = []
		for col in list(self.all):
			if(type(col) != np.int64 ):
				subset.append(col)
		self.subset = self.all[subset]
		self.subset.to_csv(fname, sep = "\t", index = False)

	def addPSVs(self):
		self.numPSVs = []
		psv = self.mydir + "mi.gml.cuts"
		self.numPSVs = []
		if(os.path.exists(psv)):
			f = open(psv)
			for idx, line in enumerate(f):
				line = line.strip()
				line = line.split("\t")
				self.numPSVs.append( len(line) )
		
		temp = pd.DataFrame({"numPSVs":self.numPSVs, "CC_ID":self.ids})
		self.all = pd.merge( self.all, temp, how='left', on ="CC_ID")
		self.all["totalPSVs"] = sum(self.numPSVs)

	def addCommon(self):
		self.collapse = os.path.basename(self.mydir[:-1])
		ref = list(SeqIO.parse(self.mydir + "ref.fasta", "fasta"))[0]
		self.collapseLen = len( ref.seq )
		self.refRegions = []
		lens = []
		dups = self.mydir + "ref.fasta.bed"
		if(os.path.exists(dups)):
			f = open(dups)
			for dup in f:
				dup = dup.strip()
				match = re.match("(.*)\t(\d+)\t(\d+)", dup)
				chr = match.group(1)
				start = int( match.group(2))
				end = int(match.group(3))
				lens.append(end-start)
				self.refRegions.append("{}:{}-{}".format(chr, start, end))
		self.aveRefLength = np.mean(lens)
	

		self.all["copiesInRef"] = len(self.refRegions) 
		self.all["numOfCCgroups"] = len(self.ids)
		self.all["numOfAssemblies"] = self.numPR + self.numR
		self.all["numF"] = self.numF
		self.all["numMA"] = self.numMA
		self.all["numPR"] = self.numPR
		self.all["numR"] = self.numR
		self.all["collapse"] = self.collapse
		self.all["collapseLen"] = self.collapseLen 
		self.all["aveRefLength"] = self.aveRefLength
		self.all["refRegions"] = ";".join(self.refRegions)

	def truthMatrix(self):
		tm = self.mydir + "truth.matrix"
		if( os.path.exists(tm) ):
			tm = pd.read_table(tm, header=None, skiprows=1, sep = '\s+')
			tm.rename(columns={0: 'CC_ID'}, inplace=True)
			self.all = pd.merge( self.all, tm, how='left', on ="CC_ID")

	def addStatus(self):
		status = []
		self.numMA = 0
		self.numR = 0
		self.numPR = 0
		self.numF = 0
		for x in self.ids:
			if( sum(self.all["CC_ID"]==x) > 1 ):
				status.append("Multiple Assemblies")
				self.numMA += 1
			elif(x in self.failed or self.asms[self.asms.CC_ID == x]["bestPerID"].iloc[0] < 0.95 ):
				status.append("Failed")
				self.numF += 1
			elif( self.asms[self.asms.CC_ID == x]["bestPerID"].iloc[0] < 0.998 ):
				status.append("Partially Resolved")
				self.numPR += 1
			else:
				status.append("Resolved")
				self.numR += 1
		add = pd.DataFrame({"CC_ID":self.ids, "Status":status})
		self.all = pd.merge( self.all, add, how='left', on ="CC_ID")

	def fillInFailed(self):
		self.failed = list( set(self.ids) - set(self.asms.CC_ID)   )
		self.fails = None
		names = list(self.asms)
		fails = []
		for fail_ID in self.failed:
			dic = {}
			for name in names:
				dic[name] = "NA"
			dic["CC_ID"] = fail_ID
			rtn = pd.Series(dic)
			fails.append(rtn)
		if(len(self.failed) > 0):
			self.fails = pd.concat(fails, axis = 1,ignore_index=True).T 
			self.all=pd.concat([self.fails, self.asms], ignore_index=True)
		else:
			self.all = self.asms
		self.all.sort_values("CC_ID", inplace=True)

	def determineGroups(self):
		vcfs = glob.glob(self.mydir + "group.*.vcf")
		self.ids = []
		self.groups = {}
		for vcf in vcfs:
			match = re.match(".*group\.(\d*)\.vcf$", vcf)
			ID = int(match.group(1))
			self.ids.append(ID)
			self.groups[ID] = "{}group.{}/".format(self.mydir,ID)
		self.ids = sorted(self.ids)
	
	def findAsm(self):
		asms = []
		for idx in self.ids:
			asmPath = self.groups[idx] + "WH.assembly.consensus.fasta" 
			m5Paths={}
			m5Paths["best"] = self.groups[idx] + "WH.best.m5" 
			m5Paths["average"] = self.groups[idx] + "WH.average.m5"
			asm = Asm(asmPath, m5Paths, idx)
			asms.append(asm.pd)
		self.asms = pd.concat(asms,ignore_index=True)






#LocalAssembly("/net/eichler/vol21/projects/bac_assembly/nobackups/genomeWide/Mitchell_CHM1/LocalAssemblies/000000F.6046000.6065699")


